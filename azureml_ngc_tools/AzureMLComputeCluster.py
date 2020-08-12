#!/usr/bin/env python3
from azureml.core import Experiment
from azureml.core.compute import AmlCompute
from azureml.train.estimator import Estimator
from .utils.port_forward_utils import port_forward_logger

import time, os, subprocess, logging
import pathlib

logger = logging.getLogger("azureml_ngc")


class AzureMLComputeCluster:
    """ Deploy a Dask cluster using Azure ML

    This creates a dask scheduler and workers on an Azure ML Compute Target.

    Parameters
    ----------
    workspace: azureml.core.Workspace (required)
        Azure ML Workspace - see https://aka.ms/azureml/workspace

    compute_target: azureml.core.ComputeTarget (required)
        Azure ML Compute Target - see https://aka.ms/azureml/computetarget

    environment_definition: azureml.core.Environment (required)
        Azure ML Environment - see https://aka.ms/azureml/environments

    experiment_name: str (optional)
        The name of the Azure ML Experiment used to control the cluster.

        Defaults to ``dask-cloudprovider``.

    initial_node_count: int (optional)
        The initial number of nodes for the Dask Cluster.

        Defaults to ``1``.

    jupyter_port: int (optional)
        Port on headnode to use for hosting JupyterLab session.

        Defaults to ``9000``.

    additional_ports: list[tuple[int, int]] (optional)
        Additional ports to forward. This requires a list of tuples where the first element
        is the port to open on the headnode while the second element is the port to map to
        or forward via the SSH-tunnel.

        Defaults to ``[]``.

    admin_username: str (optional)
        Username of the admin account for the AzureML Compute.
        Required for runs that are not on the same VNET. Defaults to empty string.
        Throws Exception if machine not on the same VNET.

        Defaults to ``""``.

    admin_ssh_key: str (optional)
        Location of the SSH secret key used when creating the AzureML Compute.
        The key should be passwordless if run from a Jupyter notebook.
        The ``id_rsa`` file needs to have 0700 permissions set.
        Required for runs that are not on the same VNET. Defaults to empty string.
        Throws Exception if machine not on the same VNET.

        Defaults to ``""``.

    telemetry_opt_out: bool (optional)
        A boolean parameter. Defaults to logging a version of AzureMLCluster
        with Microsoft. Set this flag to False if you do not want to share this
        information with Microsoft. Microsoft is not tracking anything else you
        do in your Dask cluster nor any other information related to your
        workload.

    asynchronous: bool (optional)
        Flag to run jobs asynchronously.

    **kwargs: dict
        Additional keyword arguments.
    """

    def __init__(
        self,
        workspace,
        compute_target,
        environment_definition,
        experiment_name=None,
        initial_node_count=None,
        jupyter=None,
        jupyter_port=None,
        additional_ports=None,
        admin_username=None,
        admin_ssh_key=None,
        telemetry_opt_out=None,
        **kwargs,
    ):
        ### REQUIRED PARAMETERS
        self.workspace = workspace
        self.compute_target = compute_target
        self.environment_definition = environment_definition

        ### EXPERIMENT DEFINITION
        self.experiment_name = experiment_name
        self.tags = {"tag": "azureml-ngc-tools"}

        ### ENVIRONMENT AND VARIABLES
        self.initial_node_count = initial_node_count

        ### SEND TELEMETRY
        self.telemetry_opt_out = telemetry_opt_out
        self.telemetry_set = False

        ### GPU RUN INFO
        self.workspace_vm_sizes = AmlCompute.supported_vmsizes(self.workspace)
        self.workspace_vm_sizes = [
            (e["name"].lower(), e["gpus"]) for e in self.workspace_vm_sizes
        ]
        self.workspace_vm_sizes = dict(self.workspace_vm_sizes)

        self.compute_target_vm_size = self.compute_target.serialize()["properties"][
            "status"
        ]["vmSize"].lower()
        self.n_gpus_per_node = self.workspace_vm_sizes[self.compute_target_vm_size]
        self.use_gpu = True if self.n_gpus_per_node > 0 else False

        ### JUPYTER AND PORT FORWARDING
        self.jupyter = jupyter
        self.jupyter_port = jupyter_port
        self.portforward_proc = None
        self.end_logging = False  # FLAG FOR STOPPING THE port_forward_logger THREAD

        if additional_ports is not None:
            if type(additional_ports) != list:
                error_message = (
                    f"The additional_ports parameter is of {type(additional_ports)}"
                    " type but needs to be a list of int tuples."
                    " Check the documentation."
                )
                logger.exception(error_message)
                raise TypeError(error_message)

            if len(additional_ports) > 0:
                if type(additional_ports[0]) != tuple:
                    error_message = (
                        f"The additional_ports elements are of {type(additional_ports[0])}"
                        " type but needs to be a list of int tuples."
                        " Check the documentation."
                    )
                    raise TypeError(error_message)

                ### check if all elements are tuples of length two and int type
                all_correct = True
                for el in additional_ports:
                    if type(el) != tuple or len(el) != 2:
                        all_correct = False
                        break

                    if (type(el[0]), type(el[1])) != (int, int):
                        all_correct = False
                        break

                if not all_correct:
                    error_message = (
                        f"At least one of the elements of the additional_ports parameter"
                        " is wrong. Make sure it is a list of int tuples."
                        " Check the documentation."
                    )
                    raise TypeError(error_message)

        self.additional_ports = [] if additional_ports is None else additional_ports

        self.admin_username = admin_username
        self.admin_ssh_key = admin_ssh_key

        ### FUTURE EXTENSIONS
        self.kwargs = kwargs

        ### ABSOLUTE PATH
        self.abs_path = pathlib.Path(__file__).parent.absolute()

        # ### close the cluster handler
        # signal.signal(signal.SIGINT, self.__signal_handler)

        ### define script parameters
        self.script_params = {}
        self.script_params["--use_gpu"] = self.use_gpu
        self.script_params["--n_gpus_per_node"] = self.n_gpus_per_node

        ### headnode info
        self.headnode_info = {}

        if not self.telemetry_opt_out:
            self.__append_telemetry()

        self.__create_cluster()
        self.__print_message("Cluster created...")

    # def __signal_handler(self, signal, frame):
    #     print()
    #     self.__print_message("Closing the cluster...")
    #     self._close()

    #     if os.name == 'nt':
    #         sys.exit(0)

    def __append_telemetry(self):
        if not self.telemetry_set:
            self.telemetry_set = True
            try:
                from azureml._base_sdk_common.user_agent import append

                append("AzureML-NGC-Tools", "0.1")
            except ImportError:
                pass

    def __print_message(self, msg, length=80, filler="#", pre_post=""):
        logger.info(msg)

    def __create_cluster(self):
        print("\n")
        self.__print_message("Setting up cluster")

        exp = Experiment(self.workspace, self.experiment_name)
        estimator = Estimator(
            os.path.join(self.abs_path, "setup"),
            compute_target=self.compute_target,
            entry_script="start_jupyter.py",
            environment_definition=self.environment_definition,
            script_params=self.script_params,
            node_count=1,  ### start only scheduler
            use_docker=True,
        )
        run = exp.submit(estimator, tags=self.tags)
        self.run = run
        self.status = "running"

        self.__print_message("Waiting for compute cluster's IP")
        while (
            run.get_status() != "Canceled"
            and run.get_status() != "Failed"
            and "jupyter"
            not in run.get_metrics()  # and "scheduler" not in run.get_metrics()
        ):
            print(".", end="")
            # logger.info("Compute Cluster not ready")
            time.sleep(5)

        if run.get_status() == "Canceled" or run.get_status() == "Failed":
            logger.exception("Failed to start the AzureML Compute Cluster")
            raise Exception("Failed to start the AzureML Compute Cluster.")

        print()
        self.__print_message("Jupyter session is running...")
        print("\n\n")

        self.__setup_port_forwarding()
        self.__update_links()

        self.__print_message("Connections established")

    def __update_links(self):
        hostname = "localhost"
        location = self.workspace.get_details()["location"]
        token = self.run.get_metrics()["token"]

        self.headnode_info[
            "jupyter_url"
        ] = f"http://{hostname}:{self.jupyter_port}/?token={token}"

        logger.info(f'Jupyter URL:   {self.headnode_info["jupyter_url"]}')

    def __setup_port_forwarding(self):
        jupyter_address = self.run.get_metrics()["jupyter"]
        headnode_ip = self.run.get_metrics()["jupyter"].split(":")[0]

        headnode_public_ip = self.compute_target.list_nodes()[0]["publicIpAddress"]
        headnode_public_port = self.compute_target.list_nodes()[0]["port"]
        self.__print_message("headnode_public_ip: {}".format(headnode_public_ip))
        self.__print_message("headnode_public_port: {}".format(headnode_public_port))

        cmd = (
            "ssh -vvv -o StrictHostKeyChecking=no -N"
            f" -i {os.path.expanduser(self.admin_ssh_key)}"
            f" -L 0.0.0.0:{self.jupyter_port}:{headnode_ip}:8888"
        )

        cmd += f" {self.admin_username}@{headnode_public_ip} -p {headnode_public_port}"

        self.portforward_proc = subprocess.Popen(
            cmd.split(),
            universal_newlines=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )

        ### Starting thread to keep the SSH tunnel open on Windows
        self.portforward_logg = port_forward_logger(self.portforward_proc)
        self.portforward_logg.start()

    @property
    def jupyter_link(self):
        """ Link to JupyterLab on running on the headnode of the cluster.
        Set ``jupyter=True`` when creating the ``AzureMLCluster``.
        """
        try:
            link = self.headnode_info["jupyter_url"]
        except KeyError:
            return ""
        else:
            return link

    # close cluster
    def _close(self):
        if self.status == "closed":
            return

        if self.run:
            self.run.complete()
            self.run.cancel()

        self.status = "closed"
        self.__print_message("Cluster has now been closed.")

        if self.portforward_proc is not None:
            ### STOP LOGGING SSH
            self.portforward_proc.terminate()
            self.portforward_logg.join()
            self.end_logging = True

    def close(self):
        """ Close the cluster. All Azure ML Runs corresponding to the scheduler
        and worker processes will be completed. The Azure ML Compute Target will
        return to its minimum number of nodes after its idle time before scaledown.
        """
        logger.info("Closing experiment...")
        return self._close()
