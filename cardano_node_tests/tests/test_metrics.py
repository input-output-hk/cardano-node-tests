"""Tests for Prometheus metrics."""
import logging
from pathlib import Path

import allure
import pytest
import requests
from _pytest.tmpdir import TempdirFactory
from packaging import version

from cardano_node_tests.utils import cluster_nodes
from cardano_node_tests.utils import clusterlib
from cardano_node_tests.utils import helpers
from cardano_node_tests.utils.cluster_nodes import VERSIONS

LOGGER = logging.getLogger(__name__)


if VERSIONS.node < version.parse("1.25.0"):
    pytest.skip(
        f"metrics data not available for node version {VERSIONS.node}", allow_module_level=True
    )


@pytest.fixture(scope="module")
def create_temp_dir(tmp_path_factory: TempdirFactory):
    """Create a temporary dir."""
    return Path(tmp_path_factory.mktemp(helpers.get_id_for_mktemp(__file__))).resolve()


@pytest.fixture
def temp_dir(create_temp_dir: Path):
    """Change to a temporary dir."""
    with helpers.change_cwd(create_temp_dir):
        yield create_temp_dir


# use the "temp_dir" fixture for all tests automatically
pytestmark = pytest.mark.usefixtures("temp_dir")


EXPECTED_METRICS = [
    "cardano_node_metrics_Forge_adopted_int",
    "cardano_node_metrics_Forge_forge_about_to_lead_int",
    "cardano_node_metrics_Forge_forged_int",
    "cardano_node_metrics_Forge_node_is_leader_int",
    "cardano_node_metrics_Forge_node_not_leader_int",
    "cardano_node_metrics_Mem_resident_int",
    "cardano_node_metrics_RTS_gcLiveBytes_int",
    "cardano_node_metrics_RTS_gcMajorNum_int",
    "cardano_node_metrics_RTS_gcMinorNum_int",
    "cardano_node_metrics_RTS_gcticks_int",
    "cardano_node_metrics_RTS_mutticks_int",
    "cardano_node_metrics_Stat_cputicks_int",
    "cardano_node_metrics_Stat_threads_int",
    "cardano_node_metrics_blockNum_int",
    "cardano_node_metrics_blocksForgedNum_int",
    "cardano_node_metrics_currentKESPeriod_int",
    "cardano_node_metrics_delegMapSize_int",
    "cardano_node_metrics_density_real",
    "cardano_node_metrics_epoch_int",
    "cardano_node_metrics_mempoolBytes_int",
    "cardano_node_metrics_nodeIsLeaderNum_int",
    "cardano_node_metrics_nodeStartTime_int",
    "cardano_node_metrics_operationalCertificateExpiryKESPeriod_int",
    "cardano_node_metrics_operationalCertificateStartKESPeriod_int",
    "cardano_node_metrics_remainingKESPeriods_int",
    "cardano_node_metrics_slotInEpoch_int",
    "cardano_node_metrics_slotNum_int",
    "cardano_node_metrics_txsInMempool_int",
    "cardano_node_metrics_txsProcessedNum_int",
    "cardano_node_metrics_utxoSize_int",
    "ekg_server_timestamp_ms",
    "rts_gc_bytes_allocated",
    "rts_gc_bytes_copied",
    "rts_gc_cpu_ms",
    "rts_gc_cumulative_bytes_used",
    "rts_gc_current_bytes_slop",
    "rts_gc_current_bytes_used",
    "rts_gc_gc_cpu_ms",
    "rts_gc_gc_wall_ms",
    "rts_gc_init_cpu_ms",
    "rts_gc_init_wall_ms",
    "rts_gc_max_bytes_slop",
    "rts_gc_max_bytes_used",
    "rts_gc_mutator_cpu_ms",
    "rts_gc_mutator_wall_ms",
    "rts_gc_num_bytes_usage_samples",
    "rts_gc_num_gcs",
    "rts_gc_par_avg_bytes_copied",
    "rts_gc_par_max_bytes_copied",
    "rts_gc_par_tot_bytes_copied",
    "rts_gc_peak_megabytes_allocated",
    "rts_gc_wall_ms",
]


@pytest.fixture
def wait_epochs(cluster: clusterlib.ClusterLib):
    """Make sure we are not checking metrics in epoch < 3."""
    epochs_to_wait = 3 - cluster.get_last_block_epoch()
    if epochs_to_wait > 0:
        cluster.wait_for_new_epoch(new_epochs=epochs_to_wait)


def get_prometheus_metrics(port: int) -> requests.Response:
    response = requests.get(f"http://localhost:{port}/metrics")
    assert response, f"Request failed, status code {response.status_code}"
    return response


class TestPrometheus:
    """Prometheus metrics tests."""

    @allure.link(helpers.get_vcs_link())
    def test_available_metrics(
        self,
        wait_epochs,
    ):
        """Test that list of available metrics == list of expected metrics."""
        # pylint: disable=unused-argument
        prometheus_port = cluster_nodes.CLUSTER_TYPE.scripts_instances.get_instance_ports(
            cluster_nodes.get_cluster_env().instance_num
        ).prometheus_bft1

        response = get_prometheus_metrics(prometheus_port)

        metrics = response.text.strip().split("\n")
        metrics_keys = sorted(m.split(" ")[0] for m in metrics)
        assert metrics_keys == EXPECTED_METRICS, "Metrics differ"