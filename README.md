# AzureML NVIDIA GPU Cloud tools

The code contained within this repository allows pulling the images from NVIDIA GPU Cloud (NGC).

## Installation

To install this package type 

`pip install azureml-ngc-tools`

Alternatively, clone this repository and use python to install.

```
git clone https://github.com/.../azureml-ngc-tools.git
python setup.py install
```

## Configuration

Two configuration files are required:

1. A `json` file that contains the parameters to log in to AzureML Workspace and create Compute Target. **All the parameters shown below need to be provided.**

```
{
    "azureml_user":
    {
        "subscription_id": "<YOUR-SUBSCRIPTION-ID>",
        "resource_group": "<YOUR-RESOURCE-GROUP>",
        "workspace_name": "<YOUR-WORKSPACE-NAME>",
        "telemetry_opt_out": <true|false>
    },
    "aml_compute":
    {
        "ct_name":"<NAME-OF-YOUR-COMPUTE-TARGET>",
        "exp_name":"<NAME-OF-YOUR-EXPERIMENT>",
        "vm_name":"<SIZE-OF-THE-AZUREML-VM>",
        "admin_name":"<ADMINISTRATOR-NAME>",
        "min_nodes":<MINIMUM-NUMBER-OF-NODES>,
        "max_nodes":<MAXIMUM-NUMBER-OF-NODES>,
        "vm_priority": "<dedicated|lowpriority>",
        "idle_seconds_before_scaledown":<NUMBER-OF-SECONDS-TO-SCALE-DOWN>,
        "python_interpreter":"<PATH-TO-PYTHON-INTERPRETER>",
        "conda_packages":[<LIST-OF-ADDITIONAL-CONDA-OR-PIP-PACKAGES>],
        "environment_name":"<NAME-OF-ENVIRONMENT>",
        "docker_enabled":<true|false>,
        "user_managed_dependencies":<true|false>,
        "jupyter_port":<JUPYTER-PORT-FOR-FORWARDING>
    }
}

```

An example (fictitious):

```
{
    "azureml_user":
    {
        "subscription_id": "ef4455fa-3e35-433c-a410-76d7a8a9e793",
        "resource_group": "sample-rg",
        "workspace_name": "sample-ws",
        "telemetry_opt_out": false
    },
    "aml_compute":
    {
        "ct_name":"sample-ct",
        "exp_name":"sample-exp",
        "vm_name":"Standard_NC6s_v3",
        "admin_name": "sample",
        "min_nodes":0,
        "max_nodes":1,
        "vm_priority": "dedicated",
        "idle_seconds_before_scaledown":300,
        "python_interpreter":"/usr/bin/python",
        "conda_packages":["matplotlib","jupyterlab"],
        "environment_name":"sample_env",
        "docker_enabled":true,
        "user_managed_dependencies":true,
        "jupyter_port":9000
    }
}

```

2. A `json` file that contains information about the content you want to download from NGC. **The `base_dockerfile` parameter shown below needs to be provided.**

```
{
    "base_dockerfile":"<URI-TO-NGC-CONTAINER>",
    "additional_content": {
        "download_content": false,
        "unzip_content": false,
        "upload_content": false,
        "list":[
            {
                "url": <URL_TO_CONTENT>,
                "filename": <FILENAME_TO_SAVE_TO>,
                "localdirectory": <DIRECTORY_TO_EXTRACT_CONTENTS>,
                "computedirectory": <DIRECTORY_TO_UPLOAD_CONTENTS>,
                "zipped": <false|true>
            },
            ...
        ]
    }
}
```

An example:

```
{
    "base_dockerfile":"nvcr.io/nvidia/clara-train-sdk:v3.0",
    "additional_content": {
        "download_content": true,
        "unzip_content": true,
        "upload_content": true,
        "list":[
            {
                "url":"https://api.ngc.nvidia.com/v2/resources/nvidia/med/getting_started/versions/1/zip",
                "filename":"clarasdk.zip",
                "localdirectory":"clara",
                "computedirectory":"clara",
                "zipped":true
            }
        ]
    }
}
```

## Usage
Assuming that the AzureML config file is `user_config.json` and the NGC config file is `ngc_app.json`, and both of the files are located in the same folder, to create the cluster run the following code

`azureml-ngc-tools --login user_config.json --app ngc_app.json`