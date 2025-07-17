#!/bin/sh

# Copy private key from secrets
cp /run/secrets/pg_server_key.pem /tmp/pg_server_key.pem

# Set correct permissions for postgres user
chown postgres:postgres /tmp/pg_server_key.pem
chmod 600 /tmp/pg_server_key.pem

# Run PostgreSQL with the correct config as postgres user
exec gosu postgres postgres -c config_file=/etc/postgresql/postgresql.conf -c ssl_key_file='/tmp/pg_server_key.pem'
