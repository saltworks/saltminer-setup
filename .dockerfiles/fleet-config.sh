#!/bin/ash
handle_error() {
  echo "Error on line $1"
  echo "This does not affect SaltMiner container start."
  # Errors shouldn't prevent other containers from starting.
  exit 0
}

trap 'handle_error $LINENO' ERR

policy='{
  "name": "saltminer",
  "description": "Monitor SaltMiner",
  "namespace": "saltminer",
  "monitoring_enabled": [
    "logs",
    "metrics",
    "traces"
  ],
  "inactivity_timeout": 1209600,
  "is_protected": false
}'

echo "Starting Fleet SaltMiner configuration"
KIBANA_BASE_URL=$(jq -r .ApiConfig.KibanaBaseUrl /appsettings.json)
ES_USER=$(jq -r .ApiConfig.ElasticUsername /appsettings.json)
ES_PASS=$(jq -r .ApiConfig.ElasticPassword /appsettings.json)

curl --header "Content-Type: application/json" \
  --request POST \
  --header "kbn-xsrf: true" \
  -u $ES_USER:$ES_PASS \
  --data "$policy" \
  "$KIBANA_BASE_URL/api/fleet/agent_policies?sys_monitoring=true"


echo "Fleet configuration complete."
