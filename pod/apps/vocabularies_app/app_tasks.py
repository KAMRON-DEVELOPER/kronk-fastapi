import asyncio
import json
import os
import shutil
from dataclasses import dataclass
from functools import partial
from itertools import islice
from pathlib import Path
from typing import Annotated, Optional
from uuid import UUID, uuid4

import aiofiles
import aiohttp
from gcloud.aio.storage import Storage
from google.cloud import translate_v3
from google.cloud.vision_v1p4beta1 import ImageAnnotatorAsyncClient, Feature, ImageSource, Image, AnnotateImageRequest, GcsDestination, OutputConfig
from google.oauth2 import service_account
from nltk.tokenize import word_tokenize
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from taskiq import TaskiqDepends

from apps.vocabularies_app.models import SentenceModel, VocabularyModel, PhoneticModel, MeaningModel, DefinitionModel, UserVocabularyModel
from apps.vocabularies_app.schemas import DictionaryIn
from settings.my_config import get_settings, get_nlp
from settings.my_database import get_session
from settings.my_taskiq import broker
from utility.my_logger import my_logger

settings = get_settings()
nlp = get_nlp()

try:
    credentials = service_account.Credentials.from_service_account_file(filename=settings.GCP_CREDENTIALS_PATH)
except Exception as e:
    my_logger.exception(f"Exception while initializing google cloud platform credentials, e: {e}")


@broker.task
async def start_ocr_upload_pipeline(user_id: str, target_language_code: str, image_paths: list[str]):
    try:
        blob_names = []

        # Prepare (path, blob_name) pairs for uploading from local to gcs
        files = [(path, f"{user_id}/{os.path.basename(path)}") for path in image_paths]

        # Upload in chunks of 5
        for chunk in chunked(files, 5):
            tasks = []
            tasks.extend([upload(path=path, blob_name=blob_name) for path, blob_name in chunk])

            # Run 5 uploads in parallel
            results = await asyncio.gather(*tasks)
            blob_names.extend(results)

        output_prefix = f"ocr_output/{user_id}/"

        my_logger.warning(f"blob_names: {blob_names}")

        gcs_output_uri = f"gs://{settings.GCS_BUCKET_NAME}/{output_prefix}"

        # Run async batch OCR, because google vision limit is 2000 images
        for chunk in chunked(blob_names, 1000):
            await run_text_extraction(blob_names=chunk, output_uri=gcs_output_uri)

        await create_vocabulary_task.kiq(owner_id=user_id, output_prefix=output_prefix, target_language_code=target_language_code)
    except Exception as ex:
        my_logger.exception(f"start_ocr_upload_pipeline failed: {ex}")
        raise ex


@dataclass
class SentenceData:
    id: UUID
    sentence: str
    translation: str
    tokens: list[str]
    model: SentenceModel


@broker.task(task_name="create_vocabulary_task")
async def create_vocabulary_task(owner_id: str, output_prefix: str, target_language_code: str, session: Annotated[AsyncSession, TaskiqDepends(get_session)]):
    oid = UUID(owner_id)
    try:
        # Process OCR results
        original_sentences = set(await download_ocr_result(output_prefix))
        translated_sentences = []

        stmt = select(SentenceModel).where(SentenceModel.sentence.in_(original_sentences), SentenceModel.owner_id == oid)
        scalar_result = await session.scalars(stmt)
        existing_sentences = set(s.sentence for s in scalar_result.all())
        original_sentences = original_sentences - existing_sentences

        for chunk in chunked_by_characters(list(original_sentences)):
            translated_sentences.extend(await translate_text_async(chunk, target_language_code))

        sentences_data: list[SentenceData] = []
        all_tokens = set()

        for orig, trans in zip(original_sentences, translated_sentences):
            sid = uuid4()
            tokens = [clean_token(t) for t in word_tokenize(orig) if t.isalpha()]
            tokens = [t for t in tokens if t not in BASIC_WORDS]
            all_tokens.update(tokens)

            sentence_model = SentenceModel(id=sid, sentence=orig, translation=trans, target_language=target_language_code, owner_id=oid, words=[])
            sentences_data.append(SentenceData(sid, orig, trans, tokens, sentence_model))

        session.add_all([sd.model for sd in sentences_data])

        # Fetch and filter vocabulary
        existing_vocab: dict[str, VocabularyModel] = {}
        try:
            stmt = select(VocabularyModel).where(VocabularyModel.word.in_(all_tokens), VocabularyModel.target_language == target_language_code)
            scalar_result = await session.scalars(stmt)
            existing_vocab = {v.word: v for v in scalar_result.all()}
        except Exception as ex:
            my_logger.exception(f"Exception occurred while fetching existing vocabularies, e: {ex}")

        new_words = all_tokens - existing_vocab.keys()

        my_logger.warning(f"new_words: {new_words}")

        # Translate new words
        translated_map = {}
        for chunk in chunked_by_characters(list(new_words)):
            results = await translate_text_async(chunk, target_language_code)
            translated_map.update(zip(chunk, results))

        my_logger.warning(f"translated_map: {translated_map}")

        # Fetch dictionary info
        dictionary_results: list[DictionaryIn] = await asyncio.gather(*[fetch_dictionary(word) for word in new_words])
        dictionary_map: dict[str, DictionaryIn] = {w: d for w, d in zip(new_words, dictionary_results) if d}

        # Create new vocabularies
        new_vocab_map: dict[str, VocabularyModel] = {}
        for word in new_words:
            vocab = VocabularyModel(word=word, translation=translated_map.get(word, ""), target_language=target_language_code)

            dict_data = dictionary_map.get(word)
            if dict_data:
                vocab.phonetics = [PhoneticModel(text=p.text, audio=p.audio) for p in dict_data.phonetics]
                vocab.meanings = [
                    MeaningModel(
                        part_of_speech=m.part_of_speech,
                        definitions=[DefinitionModel(definition=d.definition, example=d.example) for d in m.definitions]
                    )
                    for m in dict_data.meanings
                ]

            new_vocab_map[word] = vocab

        try:
            session.add_all(new_vocab_map.values())
        except Exception as ex:
            my_logger.exception(f"Exception occurred while adding all the new vocabularies, e: {ex}")

        try:
            await session.flush()
        except Exception as ex:
            my_logger.exception(f"Exception occurred while flushing, e: {ex}")

        all_vocab: dict[str, VocabularyModel] = {**existing_vocab, **new_vocab_map}
        try:
            # Link user <-> vocabulary
            # First, find which links already exist.
            all_vocab_ids = {v.id for v in all_vocab.values()}
            existing_links_stmt = select(UserVocabularyModel.vocabulary_id).where(UserVocabularyModel.user_id == oid, UserVocabularyModel.vocabulary_id.in_(all_vocab_ids))
            existing_link_ids = set((await session.execute(existing_links_stmt)).scalars().all())

            # Then, create only the ones that are missing.
            new_user_vocab_links = [
                UserVocabularyModel(user_id=oid, vocabulary_id=vocab_id)
                for vocab_id in all_vocab_ids if vocab_id not in existing_link_ids
            ]
            if new_user_vocab_links:
                session.add_all(new_user_vocab_links)
        except Exception as ex:
            my_logger.exception(f"Exception occurred while linking vocabularies to the user, e: {ex}")

        try:
            # Link sentence <-> words
            for sd in sentences_data:
                sd.model.words.extend([all_vocab[word] for word in sd.tokens if word in all_vocab])
        except Exception as ex:
            my_logger.exception(f"Exception occurred while linking vocabularies to the sentence, e: {ex}")

        try:
            await session.commit()
        except Exception as ex:
            my_logger.exception(f"Exception occurred while commiting, e: {ex}")

        temp_dir_path = settings.TEMP_IMAGES_FOLDER_PATH / owner_id
        await asyncio.to_thread(partial(shutil.rmtree, temp_dir_path, ignore_errors=True))
        await delete_gcs_folder(settings.GCS_BUCKET_NAME, output_prefix)

        return {"ok": True}
    except Exception as ex:
        my_logger.exception(f"create_vocabulary_task failed: {ex}")
        await session.rollback()
        raise ex


# -------------------------------------------------- Helpers --------------------------------------------------
@dataclass
class SentenceData:
    """id: UUID, sentence: str, translation: str, tokens: list[str], model: SentenceModel"""
    id: UUID
    sentence: str
    translation: str
    tokens: list[str]
    model: SentenceModel


def is_complete_sentence(sentence: str) -> bool:
    """Checks if the sentence has a root verb, a strong indicator of completeness."""
    doc = nlp(sentence)
    has_root = any(token.dep_ == "ROOT" for token in doc)
    has_subject = any(token.dep_ in ("nsubj", "nsubjpass") for token in doc)
    return has_root and has_subject


def chunked(iterable, size):
    it = iter(iterable)
    while chunk := list(islice(it, size)):
        yield chunk


def chunked_by_characters(items: list[str], max_chars: int = 4500) -> list[list[str]]:
    """Chunk list of strings by character count to respect API limits"""
    chunks = []
    current_chunk = []
    current_length = 0

    for item in items:
        item_length = len(item) + 1
        if current_length + item_length > max_chars and current_chunk:
            chunks.append(current_chunk)
            current_chunk = [item]
            current_length = item_length
        else:
            current_chunk.append(item)
            current_length += item_length

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def clean_token(word: str) -> str:
    return word.lower().strip(".,!? ")


# ----------------------------------------------- GCS Operations -----------------------------------------------
async def upload(path: Path, blob_name: str):
    async with aiofiles.open(path, "rb") as f:
        file_bytes = await f.read()
    await upload_to_gcs(file_bytes=file_bytes, blob_name=blob_name)
    return blob_name


async def fetch_dictionary(word: str) -> Optional[DictionaryIn]:
    url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{word.lower()}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url=url) as response:
                if response.status == 200:
                    data: list[dict] = await response.json()

                    # Use the first entry as the base
                    merged_data = data[0]

                    # If other entries exist, merge their meanings
                    if len(data) > 1:
                        for entry in data[1:]:
                            entry_meaning = entry.get("meanings", [])
                            if entry_meaning:
                                merged_data["meanings"].extend(entry_meaning)
                    return DictionaryIn.model_validate(merged_data)
                elif response.status == 404:
                    return None
                else:
                    raise Exception(f"Dictionary API error {response.status}")
    except Exception as ex:
        my_logger.exception(f"fetch_dictionary_data failed: {ex}")
        raise ex


async def upload_to_gcs(file_bytes: bytes, blob_name: str):
    try:
        async with Storage(service_file=settings.GCP_CREDENTIALS_PATH) as client:
            await client.upload(bucket=settings.GCS_BUCKET_NAME, object_name=blob_name, file_data=file_bytes)

        my_logger.warning(f"✅ Uploaded to: gs://{settings.GCS_BUCKET_NAME}/{blob_name}")
        return f"gs://{settings.GCS_BUCKET_NAME}/{blob_name}"
    except Exception as ex:
        my_logger.exception(f"upload image failed: {ex}")
        raise ex


async def delete_gcs_folder(bucket_name: str, folder_prefix: str):
    try:
        async with Storage(service_file=settings.GCP_CREDENTIALS_PATH) as client:
            objects = await client.list_objects(bucket=bucket_name)
            for obj in objects.get("items", [{}]):
                object_name = obj.get("name", "")
                if object_name.startswith(folder_prefix):
                    await client.delete(bucket=bucket_name, object_name=object_name)
                    my_logger.warning(f"🗑️ Deleted: gs://{bucket_name}/{object_name}")
    except Exception as ex:
        my_logger.exception(f"delete_gcs_folder failed: {ex}")
        raise ex


async def download_ocr_result(output_prefix: str) -> list[str]:
    try:
        sentences: list[str] = []
        async with Storage(service_file=settings.GCP_CREDENTIALS_PATH) as client:
            objects = await client.list_objects(bucket=settings.GCS_BUCKET_NAME)
            for obj in objects.get("items", [{}]):
                object_name = obj.get("name", "")
                if object_name.startswith(output_prefix) and object_name.endswith(".json"):
                    content: bytes = await client.download(bucket=settings.GCS_BUCKET_NAME, object_name=object_name)
                    data: dict = json.loads(content.decode())
                    for response in data.get("responses", [{}]):
                        if "fullTextAnnotation" in response:
                            text = response.get("fullTextAnnotation", {}).get("text", "").strip()
                            is_complete = is_complete_sentence(text)
                            my_logger.warning(f"text: {text}, is_complete: {is_complete}")
                            if is_complete:
                                sentences.append(text)
            return sentences
    except Exception as ex:
        my_logger.exception(f"download ocr failed: {ex}")
        raise ex


# -------------------------------------------------- API Operations --------------------------------------------------
async def run_text_extraction(blob_names: list[str], output_uri: str):
    try:
        client = ImageAnnotatorAsyncClient(credentials=credentials)

        requests = [
            AnnotateImageRequest({
                "image": Image({
                    "source": ImageSource({
                        "image_uri": f"gs://{settings.GCS_BUCKET_NAME}/{blob_name}",
                    }),
                }),
                "features": [Feature({"type_": Feature.Type.DOCUMENT_TEXT_DETECTION})]
            })
            for blob_name in blob_names
        ]
        output_config = OutputConfig({"gcs_destination": GcsDestination({"uri": output_uri}), "batch_size": 10})
        operation = await client.async_batch_annotate_images(requests=requests, output_config=output_config)
        response = await operation.result()

        gcs_output_uri = response.output_config.gcs_destination.uri
        my_logger.warning(f"Output written to GCS with prefix: {gcs_output_uri}")
        my_logger.warning(f"✅ OCR complete, results saved to: {output_uri}")

    except Exception as ex:
        my_logger.exception(f"run_text_extraction failed: {ex}")
        raise ex


async def translate_text_async(contents: list[str], target_language_code: str) -> list[str]:
    try:
        client = translate_v3.TranslationServiceAsyncClient(credentials=credentials)
        parent = f"projects/{settings.GCP_PROJECT_ID}/locations/global"
        response = await client.translate_text(parent=parent, contents=contents, mime_type="text/plain", target_language_code=target_language_code)
        my_logger.warning(f"response: {response}")

        # Return a list of all translated texts
        return [t.translated_text for t in response.translations]
    except Exception as ex:
        my_logger.exception(f"translate_text_async failed: {ex}")
        raise ex


# @broker.task(task_name="create_vocabulary_task")
# async def create_vocabulary_task(owner_id: str, output_prefix: str, target_language_code: str,
#                                  session: Annotated[AsyncSession, TaskiqDepends(get_session)]):
#     try:
#         oid = UUID(hex=owner_id)
#
#         # Get original sentences from OCR results
#         original_sentences = await download_ocr_result(output_prefix=output_prefix)  # ["it is totally fine", "what did you expected?", "that was awesome!"]
#         my_logger.warning(f"original_sentences: {original_sentences}")
#         translated_sentences = []  # ["bu butunlay yaxshi", "nima kutgan edingiz?", "bu ajoyib edi"]
#
#         # Translate sentences in batches
#         for chunk in chunked_by_characters(items=original_sentences, max_chars=4500):
#             translated_sentence = await translate_text_async(contents=chunk, target_language_code=target_language_code)
#             translated_sentences.extend(translated_sentence)
#         my_logger.warning(f"translated_sentences: {translated_sentences}")
#
#         # Creating sentence models
#         sentence_ids_with_tokens: list[tuple[UUID, list[str]]] = []
#         sentence_ids_with_sentence: dict[UUID, SentenceModel] = {}
#
#         for original_text, translated_text in zip(original_sentences, translated_sentences):
#             sentence_id = uuid4()
#
#             tokens = [clean_token(token) for token in word_tokenize(original_text) if token.isalpha() and clean_token(token) not in BASIC_WORDS]
#             sentence_ids_with_tokens.append((sentence_id, tokens))
#
#             sentence = SentenceModel(id=sentence_id, sentence=original_text, translation=translated_text, target_language=target_language_code, owner_id=oid)
#             sentence_ids_with_sentence[sentence_id] = sentence
#             session.add(sentence)
#
#         my_logger.warning(f"sentence_ids_with_tokens: {sentence_ids_with_tokens}")
#         my_logger.warning(f"sentence_ids_with_sentence: {sentence_ids_with_sentence}")
#
#         # Step 4: Determine all unique new words
#         all_unique_words = set()
#         for _, words in sentence_ids_with_tokens:
#             all_unique_words.update(words)
#
#         # Step 5: Fetch existing vocabulary words
#         stmt = select(VocabularyModel.word).where(VocabularyModel.word.in_(all_unique_words), VocabularyModel.target_language == target_language_code)
#         existing_vocab_query = await session.scalars(stmt)
#         my_logger.warning(f"existing_vocab_query: {existing_vocab_query}")
#         existing_words = {row[0] for row in existing_vocab_query.all()}
#         new_words = all_unique_words - existing_words
#
#         # Step 6: Translate new words
#         translated_map: dict[str, str] = {}
#         for chunk in chunked_by_characters(items=list(new_words), max_chars=4500):
#             translated = await translate_text_async(contents=chunk, target_language_code=target_language_code)
#             for word, translated_word in zip(chunk, translated):
#                 translated_map[word] = translated_word
#
#         # Step 7: Fetch dictionary data
#         dictionary_map: dict[str, DictionaryIn] = {}
#         dictionary_tasks = [fetch_dictionary(word) for word in new_words]
#         dictionary_results: list[DictionaryIn] = await asyncio.gather(*dictionary_tasks)
#         for word, result in zip(new_words, dictionary_results):
#             if result:
#                 dictionary_map[word] = result
#
#         # Step 7.1: Bulk fetch existing vocabularies
#         existing_vocabulary_query = await session.execute(
#             select(VocabularyModel).where(VocabularyModel.word.in_(all_unique_words), VocabularyModel.target_language == target_language_code))
#         existing_vocab_map: dict[str, VocabularyModel] = {vocabulary.word: vocabulary for vocabulary in existing_vocabulary_query.scalars().all()}
#
#         # Step 7.2: Create and collect new vocabulary entries
#         new_vocab_map: dict[str, VocabularyModel] = {}
#         for word in all_unique_words:
#             if word not in existing_vocab_map:
#                 vocabulary = VocabularyModel(word=word, translation=translated_map.get(word, ""), target_language=target_language_code)
#
#                 # Attach dictionary data
#                 dict_data = dictionary_map.get(word)
#                 if dict_data:
#                     for p in dict_data.phonetics:
#                         vocabulary.phonetics.append(PhoneticModel(text=p.text, audio=p.audio))
#                     for m in dict_data.meanings:
#                         meaning = MeaningModel(part_of_speech=m.part_of_speech)
#                         for d in m.definitions:
#                             meaning.definitions.append(DefinitionModel(definition=d.definition, example=d.example))
#                         vocabulary.meanings.append(meaning)
#
#                 session.add(vocabulary)
#                 new_vocab_map[word] = vocabulary
#
#         # 3. After flush, build user ↔ vocab connections
#         await session.flush()
#
#         # Combine both vocab maps
#         all_vocab_map: dict[str, VocabularyModel] = {**existing_vocab_map, **new_vocab_map}
#
#         # 4. Create UserVocabularyModel entries
#         for word in all_unique_words:
#             vocab = all_vocab_map[word]
#             # Ensure user ↔ vocab relationship exists
#             await session.merge(UserVocabularyModel(user_id=oid, vocabulary_id=vocab.id))
#
#         # 5. Link vocabularies to sentences
#         for sentence_id, words in sentence_ids_with_tokens:
#             sentence_model = sentence_ids_with_sentence.get(sentence_id)
#             for word in words:
#                 vocab = all_vocab_map.get(word)
#                 if vocab and vocab not in sentence_model.words:
#                     sentence_model.words.append(vocab)  # type: ignore[attr-defined]
#
#         # Step 9: Save all changes
#         await session.commit()
#
#         # Step 10: Cleanup GCS folder & temp folder
#         await delete_gcs_folder(settings.GCS_BUCKET_NAME, output_prefix)
#         shutil.rmtree(settings.TEMP_IMAGES_FOLDER_PATH / owner_id, ignore_errors=True)
#
#         return {"ok": True}
#     except Exception as ex:
#         my_logger.exception(f"create_vocabulary_task failed: {ex}")
#         await session.rollback()
#         raise ex


BASIC_WORDS = {
    "the", "a", "an", "i", "you", "he", "she", "it", "we", "they", "is", "are", "was", "were", "am", "be", "been", "being", "in", "on", "at",
    "of", "for", "and", "or", "but", "so", "to", "do", "did", "does", "have", "has", "had", "with", "as", "not", "if", "also", "from", "by", "will",
    "should", "shall", "you're", "i'm", "it's", "ok", "thank", "thanks" "please", "sorry", "excuse", "hello", "hi", "bye", "goodbye", "welcome",
}
