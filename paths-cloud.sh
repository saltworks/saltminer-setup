#!/bin/bash
smcfg="/etc/saltworks/saltminer"

echo -e "\nCreating configuration files."

sudo mkdir -p $smcfg/nginx
sudo cp ./config/saltminer/nginx/nginx.conf $smcfg/nginx
sudo cp ./config/saltminer/nginx/saltminer.crt $smcfg/nginx
sudo cp ./config/saltminer/nginx/saltminer.key $smcfg/nginx


sudo mkdir $smcfg/agent
sudo mkdir $smcfg/api
sudo mkdir -p $smcfg/jobmanager/report-templates
sudo mkdir $smcfg/python
sudo mkdir $smcfg/servicemanager
sudo mkdir $smcfg/ui-api

sudo cp -r ./config/saltminer/python/* $smcfg/python
sudo cp -r ./config/saltminer/agent/SourceConfigs/ $smcfg/agent/
sudo cp ./config/saltminer/api/appsettings.json $smcfg/api
sudo cp ./config/saltminer/servicemanager/ServiceManagerSettings.json $smcfg/servicemanager
sudo cp ./config/saltminer/ui-api/appsettings.json $smcfg/ui-api
sudo cp -r ./config/saltminer/jobmanager/* $smcfg/jobmanager/
sudo cp ./config/saltminer/manager/ManagerSettings.json $smcfg/manager

sudo mkdir -p /usr/share/saltworks/saltminer/python/Custom
sudo cp -r ./config/saltminer/python-custom/* /usr/share/saltworks/saltminer/python/Custom

sudo mkdir $smcfg/kibana
sudo cp ./config/saltminer/kibana/kibana.yml $smcfg/kibana

echo -e "\nComplete.\n"
