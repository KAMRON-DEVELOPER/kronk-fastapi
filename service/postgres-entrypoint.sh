#!/bin/sh

set -e

# Copy private key from secrets
cp /run/secrets/pg-server-key.pem /tmp/pg-server-key.pem
chown postgres:postgres /tmp/pg-server-key.pem
chmod 600 /tmp/pg-server-key.pem

# Pass control to the official entrypoint
exec docker-entrypoint.sh postgres -c config_file=/etc/postgresql/postgresql.conf -c ssl_key_file='/tmp/pg-server-key.pem'