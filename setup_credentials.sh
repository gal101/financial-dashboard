#!/bin/bash

echo "Tradeville API Credentials Setup"

read -p "Enter TRADEVILLE_USER [!DemoAPITDV]: " user
if [ -z "$user" ]; then
    user="!DemoAPITDV"
fi

read -p "Enter TRADEVILLE_PASSWORD [DemoAPITDV]: " password
if [ -z "$password" ]; then
    password="DemoAPITDV"
fi

read -p "Enter TRADEVILLE_DEMO (true/false) [true]: " demo_input
if [ -z "$demo_input" ]; then
    demo="true"
else
    demo_lower=$(echo "$demo_input" | tr '[:upper:]' '[:lower:]')
    if [ "$demo_lower" = "false" ] || [ "$demo_lower" = "f" ] || [ "$demo_lower" = "0" ] || [ "$demo_lower" = "n" ] || [ "$demo_lower" = "no" ]; then
        demo="false"
    else
        demo="true"
    fi
fi

# Determine script directory
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
ENV_PATH="$DIR/.env"

cat << EOF > "$ENV_PATH"
TRADEVILLE_USER=$user
TRADEVILLE_PASSWORD=$password
TRADEVILLE_DEMO=$demo
EOF

echo "Credentials written successfully to $ENV_PATH"
