import logging

from azureml.core import Workspace, Environment
from azureml.core.conda_dependencies import CondaDependencies
from azureml.core.compute import ComputeTarget, AmlCompute

import click, os

from azureml_ngc_tools.AzureMLComputeCluster import AzureMLComputeCluster
from azureml_ngc_tools.cli import ngccontent
from azureml.exceptions._azureml_exception import ProjectSystemException

logger = logging.getLogger(__name__)


@click.command()
@click.option(
    "--login", is_flag=False, required=True, help="Path to the login config file"
)
@click.option("--app", is_flag=False, required=True, help="Path to the config file")
@click.version_option()
def start(login, app):
    login_config = ngccontent.get_config(login)
    app_config = ngccontent.get_config(app)

    ### WORKSPACE
    subscription_id = login_config["azureml_user"]["subscription_id"]
    resource_group = login_config["azureml_user"]["resource_group"]
    workspace_name = login_config["azureml_user"]["workspace_name"]

    try:
        ws = Workspace(
            workspace_name=workspace_name,
            subscription_id=subscription_id,
            resource_group=resource_group,
        )
    except ProjectSystemException:
        msg = f'\n\nThe workspace "{workspace_name}" does not exist. '
        msg += f'Go to \n\n  -->> https://docs.microsoft.com/en-us/azure/machine-learning/how-to-manage-workspace <<-- \n\n'
        msg += f'and create the workspace first.\n\n\n'
        msg += f'Your current configuration: \n\n'
        msg += f'Workspace name: {workspace_name} \n'
        msg += f'Subscription id: {subscription_id} \n'
        msg += f'Resource group: {resource_group}\n\n'
        raise Exception(msg)

    verify = f"""
    Subscription ID: {subscription_id}
    Resource Group: {resource_group}
    Workspace: {workspace_name}"""
    print(verify)

    ### experiment name
    exp_name = login_config["aml_compute"]["exp_name"]

    ### azure ml names
    ct_name = login_config["aml_compute"]["ct_name"]
    vm_name = login_config["aml_compute"]["vm_name"].lower()
    vm_priority = login_config["aml_compute"]["vm_priority"]

    ### trust but verify
    verify = f"""
    Experiment name: {exp_name}"""
    print(verify)

    ### GPU RUN INFO
    workspace_vm_sizes = AmlCompute.supported_vmsizes(ws)
    workspace_vm_sizes = [
        (e["name"].lower(), e["gpus"])
        for e in workspace_vm_sizes
        if "_nc" in e["name"].lower()
    ]
    workspace_vm_sizes = dict(workspace_vm_sizes)

    if vm_name in workspace_vm_sizes:
        # vm_name = login_config["aml_compute"]["vm_name"]
        gpus_per_node = workspace_vm_sizes[vm_name]

        verify = f"""
    Compute target: {ct_name}
    VM Size: {vm_name}
    No of GPUs: {gpus_per_node}
    Priority: {vm_priority}
        """
        print(verify)

        ### get SSH keys
        ssh_key_pub, pri_key_file = get_ssh_keys()

        if ct_name not in ws.compute_targets:
            print(f"Compute target {ct_name} does not exist...")
            config = AmlCompute.provisioning_configuration(
                vm_size=vm_name,
                min_nodes=login_config["aml_compute"]["min_nodes"],
                max_nodes=login_config["aml_compute"]["max_nodes"],
                vm_priority=vm_priority,
                idle_seconds_before_scaledown=login_config["aml_compute"][
                    "idle_seconds_before_scaledown"
                ],
                admin_username=login_config["aml_compute"]["admin_name"],
                admin_user_ssh_key=ssh_key_pub,
                remote_login_port_public_access="Enabled",
            )
            ct = ComputeTarget.create(ws, ct_name, config)
            ct.wait_for_completion(show_output=True)
        else:
            print(
                "    Loading pre-existing compute target {ct_name}".format(
                    ct_name=ct_name
                )
            )
            ct = ws.compute_targets[ct_name]
    else:
        print("Unsupported vm_size {vm_size}".format(vm_size=vm_name))
        print("The specified vm size must be one of ...")
        for azure_gpu_vm_size in workspace_vm_sizes.keys():
            print("... " + azure_gpu_vm_size)
        raise Exception(
            "{vm_size} does not have Pascal or above GPU Family".format(vm_size=vm_name)
        )

    environment_name = login_config["aml_compute"]["environment_name"]
    python_interpreter = login_config["aml_compute"]["python_interpreter"]
    conda_packages = login_config["aml_compute"]["conda_packages"]

    if environment_name not in ws.environments:
        env = Environment(name=environment_name)
        env.docker.enabled = login_config["aml_compute"]["docker_enabled"]
        env.docker.base_image = None
        env.docker.base_dockerfile = f'FROM {app_config["base_dockerfile"]}'
        env.python.interpreter_path = python_interpreter
        env.python.user_managed_dependencies = True
        conda_dep = CondaDependencies()

        for conda_package in conda_packages:
            conda_dep.add_conda_package(conda_package)

        env.python.conda_dependencies = conda_dep
        env.register(workspace=ws)
        evn = env
    else:
        env = ws.environments[environment_name]

    amlcluster = AzureMLComputeCluster(
        workspace=ws,
        compute_target=ct,
        initial_node_count=1,
        experiment_name=login_config["aml_compute"]["exp_name"],
        environment_definition=env,
        jupyter_port=login_config["aml_compute"]["jupyter_port"],
        telemetry_opt_out=True,
        admin_username=login_config["aml_compute"]["admin_name"],
        admin_ssh_key=pri_key_file,
    )

    print(f"\n    Go to: {amlcluster.jupyter_link}")
    print("    Press Ctrl+C to stop the cluster.")


def get_ssh_keys():
    from cryptography.hazmat.primitives import serialization as crypto_serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.backends import default_backend as crypto_default_backend

    dir_path = os.path.join(os.getcwd(), ".ssh")

    if not os.path.exists(dir_path):
        os.makedirs(dir_path)

    pub_key_file = os.path.join(dir_path, "key.pub")
    pri_key_file = os.path.join(dir_path, "key")

    keys_exist = True

    if not os.path.exists(pub_key_file):
        print("Public SSH key does not exist!")
        keys_exist = False

    if not os.path.exists(pri_key_file):
        print("Private SSH key does not exist!")
        keys_exist = False

    if not keys_exist:
        key = rsa.generate_private_key(
            backend=crypto_default_backend(), public_exponent=65537, key_size=2048
        )

        private_key = key.private_bytes(
            crypto_serialization.Encoding.PEM,
            crypto_serialization.PrivateFormat.PKCS8,
            crypto_serialization.NoEncryption(),
        )
        public_key = key.public_key().public_bytes(
            crypto_serialization.Encoding.OpenSSH,
            crypto_serialization.PublicFormat.OpenSSH,
        )

        with open(pub_key_file, "wb") as f:
            f.write(public_key)

        with open(pri_key_file, "wb") as f:
            f.write(private_key)

        os.chmod(pri_key_file, 0o600)

    with open(pub_key_file, "r") as f:
        pubkey = f.read()

    return pubkey, pri_key_file


def go():
    start()


if __name__ == "__main__":
    go()
