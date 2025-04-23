#!/bin/bash
smcfg="/etc/saltworks/saltminer"

echo -e "\nCreating configuration files."

sudo mkdir -p $smcfg/nginx
sudo cp ./nginx.conf $smcfg/nginx
sudo cp ./saltminer.crt $smcfg/nginx
sudo cp ./saltminer.key $smcfg/nginx


sudo mkdir $smcfg/agent
sudo mkdir $smcfg/api
sudo mkdir -p $smcfg/jobmanager/report-templates
sudo mkdir $smcfg/python
sudo mkdir $smcfg/ui-api

sudo cp -r ./config/saltminer/python/* $smcfg/python
sudo cp -r ./config/saltminer/agent/SourceConfigs/ $smcfg/agent/
sudo cp ./config/saltminer/api/appsettings.json $smcfg/api
sudo cp ./config/saltminer/ui-api/appsettings.json $smcfg/ui-api
sudo cp -r ./config/saltminer/jobmanager/* $smcfg/jobmanager/

echo -e "\nComplete.\n"
