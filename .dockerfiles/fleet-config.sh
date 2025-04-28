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

echo -e "Starting Fleet SaltMiner configuration\n"
KIBANA_BASE_URL=$(jq -r .ApiConfig.KibanaBaseUrl /appsettings.json)
ES_USER=$(jq -r .ApiConfig.ElasticUsername /appsettings.json)
ES_PASS=$(jq -r .ApiConfig.ElasticPassword /appsettings.json)

echo -e "Registering agent policy\n"
agent_policy_response=$(curl --header "Content-Type: application/json" \
  --request POST \
  --header "kbn-xsrf: true" \
  -u $ES_USER:$ES_PASS \
  --data "$policy" \
  "$KIBANA_BASE_URL/api/fleet/agent_policies?sys_monitoring=true")

policy_id=$(echo "$agent_policy_response" | jq -r '.item.id')
echo "Policy ID: $policy_id"

echo -e "Creating package policy"
jq --arg id $policy_id '.policy_ids[] = $id' /scripts/package-policies.json > /scripts/package-policies.json.new
mv /scripts/package-policies.json /scripts/package-policies.json.old
mv /scripts/package-policies.json.new /scripts/package-policies.json
package_policy=$(cat /scripts/package-policies.json)
curl --header "Content-Type: application/json" \
  --request POST \
  --header "kbn-xsrf: true" \
  -u $ES_USER:$ES_PASS \
  --data "$package_policy" \
  "$KIBANA_BASE_URL/api/fleet/package_policies"


echo -e "\nEnrollment key acquisition\n"
key_response=$(curl \
 --request GET "$KIBANA_BASE_URL/api/fleet/enrollment_api_keys" \
 -u $ES_USER:$ES_PASS)

TOKEN=$(echo $key_response | jq -r --arg policy_id $policy_id '.list[] | select(.active==true and .policy_id == $policy_id) | .api_key')

tee /fleet-enroll-token << EOF
FLEET_ENROLLMENT_TOKEN=$TOKEN
FLEET_HOST=$KIBANA_BASE_URL
EOF

echo "Fleet configuration complete."
