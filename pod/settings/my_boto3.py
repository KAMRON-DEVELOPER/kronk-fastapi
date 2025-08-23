import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import aioboto3
from botocore.exceptions import ClientError

from settings.my_config import get_settings
from utility.my_logger import my_logger

settings = get_settings()

session = aioboto3.Session()


@asynccontextmanager
async def s3_client():
    async with session.client(
            service_name="s3",
            endpoint_url=f"{'http' if settings.DEBUG else 'https'}://{settings.S3_ENDPOINT}",
            aws_access_key_id=settings.S3_ACCESS_KEY_ID,
            aws_secret_access_key=settings.S3_SECRET_KEY,
            region_name=settings.S3_REGION,
            verify=False if settings.DEBUG else True,
    ) as client:
        yield client


async def initialize_boto3():
    bucket_name = settings.S3_BUCKET_NAME
    async with s3_client() as s3:
        try:
            await s3.head_bucket(Bucket=bucket_name)
            my_logger.info(f"Bucket '{bucket_name}' already exists.")
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code")
            if error_code == "404":
                my_logger.info(f"Bucket '{bucket_name}' not found. Creating...")
                await s3.create_bucket(Bucket=bucket_name, CreateBucketConfiguration={"LocationConstraint": settings.S3_REGION})
                my_logger.info(f"Bucket '{bucket_name}' created.")
            else:
                my_logger.error(f"Error checking for bucket: {e}")
                raise

        try:
            if settings.DEBUG:
                return

            current_policy_str = await s3.get_bucket_policy(Bucket=bucket_name)
            current_policy = json.loads(current_policy_str["Policy"])

            if current_policy == desired_policy:
                my_logger.info("✅ Bucket policy is already correct.")
            else:
                my_logger.warning("⚠️ Bucket policy mismatch. Updating...")
                await s3.put_bucket_policy(Bucket=bucket_name, Policy=json.dumps(desired_policy))
                my_logger.info("✅ Bucket policy updated.")

        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchBucketPolicy":
                my_logger.warning("⚠️ No bucket policy found. Setting it now.")
                await s3.put_bucket_policy(Bucket=bucket_name, Policy=json.dumps(desired_policy))
                my_logger.info("✅ Bucket policy has been set.")
            else:
                my_logger.error(f"Unhandled S3Error while getting policy: {e}")
                raise


async def get_object_from_boto3(object_name: str) -> bytes:
    async with s3_client() as s3:
        try:
            response = await s3.get_object(Bucket=settings.S3_BUCKET_NAME, Key=object_name)
            return await response["Body"].read()
        except ClientError as e:
            my_logger.error(f"Failed to get object '{object_name}': {e}")
            raise ValueError(f"Could not retrieve object: {e}")


async def put_object_to_boto3(object_name: str, data: bytes, content_type: str, old_object_name: Optional[str] = None, for_update: bool = False) -> str:
    async with s3_client() as s3:
        try:
            if for_update and old_object_name:
                await s3.delete_object(Bucket=settings.S3_BUCKET_NAME, Key=old_object_name)

            await s3.put_object(Bucket=settings.S3_BUCKET_NAME, Key=object_name, Body=data, ContentType=content_type, ContentLength=len(data))
            return object_name
        except ClientError as e:
            my_logger.error(f"Failed to put object '{object_name}': {e}")
            raise ValueError(f"Could not upload object: {e}")


async def put_file_to_boto3(object_name: str, file_path: Path, content_type: str, old_object_name: Optional[str] = None, for_update=False) -> str:
    async with s3_client() as s3:
        try:
            if for_update and old_object_name:
                await s3.delete_object(Bucket=settings.S3_BUCKET_NAME, Key=old_object_name)

            my_logger.debug(f"Uploading file: {file_path} as {object_name}")

            await s3.upload_file(Filename=str(file_path), Bucket=settings.S3_BUCKET_NAME, Key=object_name, ExtraArgs={"ContentType": content_type})
            return object_name
        except ClientError as e:
            my_logger.error(f"Failed to upload file '{file_path}': {e}")
            raise ValueError(f"Could not upload file: {e}")
        except FileNotFoundError:
            my_logger.error(f"File not found for upload: {file_path}")
            raise


async def remove_objects_from_boto3(object_names: list[str]) -> None:
    async with s3_client() as s3:
        if not object_names:
            return
        try:
            objects_to_delete = [{"Key": name} for name in object_names]
            my_logger.debug(f"Removing {len(objects_to_delete)} objects from S3.")
            await s3.delete_objects(Bucket=settings.S3_BUCKET_NAME, Delete={"Objects": objects_to_delete})
        except ClientError as e:
            my_logger.error(f"Failed to remove objects: {e}")
            raise


async def wipe_objects_from_boto3(user_id: str) -> None:
    async with s3_client() as s3:
        try:
            paginator = s3.get_paginator("list_objects_v2")
            object_keys_to_delete = []
            async for page in paginator.paginate(Bucket=settings.S3_BUCKET_NAME, Prefix=f"users/{user_id}/"):
                if "Contents" in page:
                    for obj in page["Contents"]:
                        object_keys_to_delete.append(obj["Key"])

            if object_keys_to_delete:
                await remove_objects_from_boto3(object_keys_to_delete)
            else:
                my_logger.info(f"No objects found to wipe for user '{user_id}'.")

        except ClientError as e:
            my_logger.error(f"Failed to wipe objects for user '{user_id}': {e}")
            raise ValueError(f"Could not wipe user objects: {e}")


desired_policy = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "PublicReadGetObject",
            "Effect": "Allow",
            "Principal": "*",
            "Action": ["s3:GetObject"],
            "Resource": f"arn:aws:s3:::{settings.S3_BUCKET_NAME}/*",
        }
    ],
}
