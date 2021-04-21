import argparse
import json
import os
import platform
import signal
import subprocess
import tarfile

import requests
import time
import urllib.request
import zipfile
from collections import OrderedDict
from datetime import datetime
from pathlib import Path

from psutil import process_iter

NODE = "./cardano-node"
CLI = "./cardano-cli"
ROOT_TEST_PATH = ""

MAINNET_EXPLORER_URL = "https://explorer.cardano.org/graphql"
STAGING_EXPLORER_URL = "https://explorer.staging.cardano.org/graphql"
TESTNET_EXPLORER_URL = "https://explorer.cardano-testnet.iohkdev.io/graphql"
SHELEY_QA_EXPLORER_URL = "https://explorer.shelley-qa.dev.cardano.org/graphql"


def set_repo_paths():
    global ROOT_TEST_PATH
    ROOT_TEST_PATH = Path.cwd()

    print(f"ROOT_TEST_PATH: {ROOT_TEST_PATH}")


def get_epoch_start_datetime(env, epoch_no):
    global res
    headers = {'Content-type': 'application/json'}
    payload = '{"query":"query searchForEpochByNumber($number: Int!) {\\n  epochs(where: {number: ' \
              '{_eq: $number}}) {\\n    ...EpochOverview\\n  }\\n}\\n\\nfragment EpochOverview on ' \
              'Epoch {\\n  blocks(limit: 1) {\\n    protocolVersion\\n  }\\n  blocksCount\\n  ' \
              'lastBlockTime\\n  number\\n  startedAt\\n  output\\n  transactionsCount\\n}\\n",' \
              '"variables":{"number":' + str(epoch_no) + '}} '

    if env == "mainnet":
        url = MAINNET_EXPLORER_URL
        res = requests.post(url, data=payload, headers=headers)
    elif env == "staging":
        url = STAGING_EXPLORER_URL
        res = requests.post(url, data=payload, headers=headers)
    elif env == "testnet":
        url = TESTNET_EXPLORER_URL
        res = requests.post(url, data=payload, headers=headers)
    elif env == "shelley_qa":
        url = SHELEY_QA_EXPLORER_URL
        res = requests.post(url, data=payload, headers=headers)
    else:
        print(f"ERROR: the provided 'env' is not supported. Please use one of: shelley_qa, "
              f"testnet, staging, mainnet")
        exit(1)

    status_code = res.status_code
    if status_code == 200:
        return res.json()['data']['epochs'][0]['startedAt']
    else:
        print(f"status_code: {status_code}")
        print(f"response: {res.text}")
        print(f"ERROR: status_code =! 200 when getting start time for epoch {epoch_no} on {env}")
        exit(1)


def git_get_commit_sha_for_tag_no(tag_no):
    global jData
    url = "https://api.github.com/repos/input-output-hk/cardano-node/tags"
    response = requests.get(url)
    if response.ok:
        jData = json.loads(response.content)
    else:
        response.raise_for_status()

    for tag in jData:
        if tag.get('name') == tag_no:
            return tag.get('commit').get('sha')

    print(f" ===== ERROR: The specified tag_no - {tag_no} - was not found ===== ")
    print(json.dumps(jData, indent=4, sort_keys=True))
    return None


def git_get_hydra_eval_link_for_commit_sha(commit_sha):
    global jData
    url = f"https://api.github.com/repos/input-output-hk/cardano-node/commits/{commit_sha}/status"
    response = requests.get(url)
    if response.ok:
        jData = json.loads(response.content)
    else:
        response.raise_for_status()

    for status in jData.get('statuses'):
        if "hydra.iohk.io/eval" in status.get("target_url"):
            return status.get("target_url")

    print(f" ===== ERROR: There is not eval link for the provided commit_sha - {commit_sha} =====")
    print(json.dumps(jData, indent=4, sort_keys=True))
    return None


def get_hydra_build_download_url(eval_url, os_type):
    global eval_jData, build_jData

    expected_os_types = ["windows", "linux", "macos"]
    if os_type not in expected_os_types:
        raise Exception(
            f" ===== ERROR: provided os_type - {os_type} - not expected - {expected_os_types}")

    headers = {'Content-type': 'application/json'}
    eval_response = requests.get(eval_url, headers=headers)

    eval_jData = json.loads(eval_response.content)

    if eval_response.ok:
        eval_jData = json.loads(eval_response.content)
    else:
        eval_response.raise_for_status()

    for build_no in eval_jData.get("builds"):
        build_url = f"https://hydra.iohk.io/build/{build_no}"
        build_response = requests.get(build_url, headers=headers)
        if build_response.ok:
            build_jData = json.loads(build_response.content)
        else:
            build_response.raise_for_status()

        if os_type.lower() == "windows":
            if build_jData.get("job") == "cardano-node-win64":
                return f"https://hydra.iohk.io/build/{build_no}/download/1/cardano-node-1.24.0-win64.zip"
        elif os_type.lower() == "linux":
            if build_jData.get("job") == "cardano-node-linux":
                return f"https://hydra.iohk.io/build/{build_no}/download/1/cardano-node-1.24.0-linux.tar.gz"
        elif os_type.lower() == "macos":
            if build_jData.get("job") == "cardano-node-macos":
                return f"https://hydra.iohk.io/build/{build_no}/download/1/cardano-node-1.24.0-macos.tar.gz"

    print(f" ===== ERROR: No build has found for the required os_type - {os_type} - {eval_url} ===")
    return None


def get_and_extract_node_files(tag_no):
    print(" - get and extract the pre-built node files")
    # os.chdir(Path(CARDANO_NODE_TESTS_PATH))
    platform_system, platform_release, platform_version = get_os_type()

    commit_sha = git_get_commit_sha_for_tag_no(tag_no)
    eval_url = git_get_hydra_eval_link_for_commit_sha(commit_sha)

    # TO DO - remove below line
    eval_url = "https://hydra.iohk.io/eval/1044305"

    print(f"commit_sha  : {commit_sha}")
    print(f"eval_url    : {eval_url}")

    if "linux" in platform_system.lower():
        download_url = get_hydra_build_download_url(eval_url, "linux")
        get_and_extract_linux_files(download_url)
    elif "darwin" in platform_system.lower():
        download_url = get_hydra_build_download_url(eval_url, "macos")
        get_and_extract_macos_files(download_url)
    elif "windows" in platform_system.lower():
        download_url = get_hydra_build_download_url(eval_url, "windows")
        get_and_extract_windows_files(download_url)


def get_and_extract_linux_files(download_url):
    # os.chdir(Path(CARDANO_NODE_TESTS_PATH))
    current_directory = os.getcwd()
    print(f" - current_directory: {current_directory}")

    archive_name = download_url.split("/")[-1].strip()

    print(f"archive_name: {archive_name}")
    print(f"download_url: {download_url}")

    urllib.request.urlretrieve(download_url, Path(current_directory) / archive_name)

    print(f" ------ listdir (before archive extraction): {os.listdir(current_directory)}")
    tf = tarfile.open(Path(current_directory) / archive_name)
    tf.extractall(Path(current_directory))
    print(f" - listdir (after archive extraction): {os.listdir(current_directory)}")


def get_and_extract_macos_files(download_url):
    os.chdir(Path(ROOT_TEST_PATH))
    current_directory = os.getcwd()
    print(f" - current_directory: {current_directory}")

    archive_name = download_url.split("/")[-1].strip()

    print(f"archive_name: {archive_name}")
    print(f"download_url: {download_url}")

    urllib.request.urlretrieve(download_url, Path(current_directory) / archive_name)

    print(f" ------ listdir (before archive extraction): {os.listdir(current_directory)}")
    tf = tarfile.open(Path(current_directory) / archive_name)
    tf.extractall(Path(current_directory))
    print(f" - listdir (after archive extraction): {os.listdir(current_directory)}")


def get_and_extract_windows_files(download_url):
    os.chdir(Path(ROOT_TEST_PATH))
    current_directory = os.getcwd()
    print(f" - current_directory: {current_directory}")

    archive_name = download_url.split("/")[-1].strip()

    print(f"archive_name: {archive_name}")
    print(f"download_url: {download_url}")

    urllib.request.urlretrieve(download_url, Path(current_directory) / archive_name)

    print(f" ------ listdir (before archive extraction): {os.listdir(current_directory)}")
    with zipfile.ZipFile(Path(current_directory) / archive_name, "r") as zip_ref:
        zip_ref.extractall(current_directory)
    print(f" ------ listdir (after archive extraction): {os.listdir(current_directory)}")


def delete_node_files():
    os.chdir(Path(ROOT_TEST_PATH))
    for p in Path(".").glob("cardano-*"):
        print(f" === deleting file: {p}")
        p.unlink(missing_ok=True)


def get_node_config_files(env):
    os.chdir(Path(ROOT_TEST_PATH))
    urllib.request.urlretrieve(
        "https://hydra.iohk.io/job/Cardano/iohk-nix/cardano-deployment/latest-finished/download/1/"
        + env
        + "-config.json",
        env + "-config.json",
        )
    urllib.request.urlretrieve(
        "https://hydra.iohk.io/job/Cardano/iohk-nix/cardano-deployment/latest-finished/download/1/"
        + env
        + "-byron-genesis.json",
        env + "-byron-genesis.json",
        )
    urllib.request.urlretrieve(
        "https://hydra.iohk.io/job/Cardano/iohk-nix/cardano-deployment/latest-finished/download/1/"
        + env
        + "-shelley-genesis.json",
        env + "-shelley-genesis.json",
        )
    urllib.request.urlretrieve(
        "https://hydra.iohk.io/job/Cardano/iohk-nix/cardano-deployment/latest-finished/download/1/"
        + env
        + "-topology.json",
        env + "-topology.json",
        )


def set_node_socket_path_env_var():
    if "windows" in platform.system().lower():
        socket_path = "\\\\.\pipe\cardano-node"
    else:
        socket_path = (Path(ROOT_TEST_PATH) / "db" / "node.socket").expanduser().absolute()

    os.environ["CARDANO_NODE_SOCKET_PATH"] = str(socket_path)


def get_os_type():
    return [platform.system(), platform.release(), platform.version()]


def get_testnet_value():
    env = vars(args)["environment"]
    if env == "mainnet":
        return "--mainnet"
    elif env == "testnet":
        return "--testnet-magic 1097911063"
    elif env == "staging":
        return "--testnet-magic 633343913"
    elif env == "shelley_qa":
        return "--testnet-magic 3"
    else:
        return None


def wait_for_node_to_start(tag_no):
    # when starting from clean state it might take ~30 secs for the cli to work
    # when starting from existing state it might take >5 mins for the cli to work (opening db and
    # replaying the ledger)
    tip = get_current_tip(tag_no, True)
    count = 0
    while tip == 1:
        time.sleep(10)
        count += 1
        tip = get_current_tip(tag_no, True)
        if count >= 540:  # 90 mins
            print(" **************  ERROR: waited 90 mins and CLI is still not usable ********* ")
            print(f"      TIP: {get_current_tip(tag_no)}")
            exit(1)
    print(f"************** CLI became available after: {count * 10} seconds **************")
    return count * 10


def get_current_tip(tag_no, wait=False):
    # tag_no should have this format: 1.23.0, 1.24.1, etc
    os.chdir(Path(ROOT_TEST_PATH))

    if int(tag_no.split(".")[1]) < 24:
        cmd = CLI + " shelley query tip " + get_testnet_value()
    else:
        cmd = CLI + " query tip " + get_testnet_value()
    try:
        output = (
            subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT)
                .decode("utf-8")
                .strip()
        )
        output_json = json.loads(output)

        print(f"output_json: {output_json}")

        if output_json["epoch"] is not None:
            output_json["epoch"] = int(output_json["epoch"])

        return output_json["epoch"], int(output_json["block"]), output_json["hash"], \
               int(output_json["slot"]), output_json["era"]
    except subprocess.CalledProcessError as e:
        if wait:
            return int(e.returncode)
        else:
            raise RuntimeError(
                "command '{}' return with error (code {}): {}".format(
                    e.cmd, e.returncode, " ".join(str(e.output).split())
                )
            )


def get_node_version():
    # os.chdir(Path(CARDANO_NODE_TESTS_PATH))
    try:
        cmd = CLI + " --version"
        output = (
            subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT)
                .decode("utf-8")
                .strip()
        )
        cardano_cli_version = output.split("git rev ")[0].strip()
        cardano_cli_git_rev = output.split("git rev ")[1].strip()
        return str(cardano_cli_version), str(cardano_cli_git_rev)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            "command '{}' return with error (code {}): {}".format(
                e.cmd, e.returncode, " ".join(str(e.output).split())
            )
        )


def start_node_windows(env, tag_no):
    os.chdir(Path(ROOT_TEST_PATH))
    current_directory = Path.cwd()
    cmd = \
        NODE + \
        " run --topology " + \
        env + \
        "-topology.json --database-path db --port 3000 --config " + \
        env + \
        "-config.json --socket-path \\\\.\pipe\cardano-node "
    logfile = open("logfile.log", "w+")
    print(f"cmd: {cmd}")

    try:
        p = subprocess.Popen(cmd, stdout=logfile, stderr=subprocess.PIPE)
        print("waiting for db folder to be created")
        count = 0
        count_timeout = 299
        while not os.path.isdir(current_directory / "db"):
            time.sleep(1)
            count += 1
            if count > count_timeout:
                print(
                    f"ERROR: waited {count_timeout} seconds and the DB folder was not created yet")
                exit(1)

        print(f"DB folder was created after {count} seconds")
        secs_to_start = wait_for_node_to_start(tag_no)
        print(f" - listdir current_directory: {os.listdir(current_directory)}")
        print(f" - listdir db: {os.listdir(current_directory / 'db')}")
        return secs_to_start
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            "command '{}' return with error (code {}): {}".format(
                e.cmd, e.returncode, ' '.join(str(e.output).split())))


def start_node_unix(env, tag_no):
    # os.chdir(Path(CARDANO_NODE_TESTS_PATH))
    current_directory = Path.cwd()

    cmd = (
        f"{NODE} run --topology {env}-topology.json --database-path "
        f"{Path(ROOT_TEST_PATH) / 'db'} "
        f"--host-addr 0.0.0.0 --port 3000 --config "
        f"{env}-config.json --socket-path ./db/node.socket"
    )

    logfile = open("logfile.log", "w+")
    print(f"cmd: {cmd}")

    try:
        p = subprocess.Popen(cmd.split(" "), stdout=logfile, stderr=subprocess.PIPE)
        print("waiting for db folder to be created")
        count = 0
        count_timeout = 299
        while not os.path.isdir(current_directory / "db"):
            time.sleep(1)
            count += 1
            if count > count_timeout:
                print(
                    f"ERROR: waited {count_timeout} seconds and the DB folder was not created yet")
                exit(1)

        print(f"DB folder was created after {count} seconds")
        secs_to_start = wait_for_node_to_start(tag_no)
        print(f" - listdir current_directory: {os.listdir(current_directory)}")
        print(f" - listdir db: {os.listdir(current_directory / 'db')}")
        return secs_to_start
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            "command '{}' return with error (code {}): {}".format(
                e.cmd, e.returncode, " ".join(str(e.output).split())
            )
        )


def stop_node():
    for proc in process_iter():
        if "cardano-node" in proc.name():
            print(f" --- Killing the `cardano-node` process - {proc}")
            proc.send_signal(signal.SIGTERM)
            proc.terminate()
            proc.kill()
    time.sleep(10)
    for proc in process_iter():
        if "cardano-node" in proc.name():
            print(f" --- ERROR: `cardano-node` process is still active - {proc}")


def percentage(part, whole):
    return round(100 * float(part) / float(whole), 2)


def get_current_date_time():
    now = datetime.now()
    return now.strftime("%d/%m/%Y %H:%M:%S")


def get_file_creation_date(path_to_file):
    return time.ctime(os.path.getmtime(path_to_file))


def get_size(start_path='.'):
    # returns directory size in bytes
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(start_path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            total_size += os.path.getsize(fp)
    return total_size


def wait_for_node_to_sync(env, tag_no):
    eras_start_time_dict = OrderedDict()
    count = 0

    # TODO: remove below line
    # latest_slot_no = get_calculated_slot_no(env)
    latest_slot_no = 20877064

    actual_epoch, actual_block, actual_hash, actual_slot, actual_era = get_current_tip(tag_no)

    start_sync = time.perf_counter()

    while actual_slot <= latest_slot_no:
        print(f"actual_era  : {actual_era} "
              f" - actual_epoch: {actual_epoch} "
              f" - actual_block: {actual_block} "
              f" - actual_slot : {actual_slot}")
        if actual_era not in eras_start_time_dict:
            if actual_epoch is None:
                # TODO: to remove this after 'tip' bug returning None/null will be fixed
                actual_epoch = 1
            actual_era_start_time = get_epoch_start_datetime(env, actual_epoch)
            actual_era_dict = {"start_epoch": actual_epoch, "start_time": actual_era_start_time}
            eras_start_time_dict[actual_era] = actual_era_dict

        time.sleep(60)
        count += 1

        actual_epoch, actual_block, actual_hash, actual_slot, actual_era = get_current_tip(tag_no)

    end_sync = time.perf_counter()

    sync_time_seconds = int(end_sync - start_sync)
    print(f"sync_time_seconds: {sync_time_seconds}")

    os.chdir(Path(ROOT_TEST_PATH) / "db" / "immutable")
    chunk_files = sorted(os.listdir(os.getcwd()), key=os.path.getmtime)
    latest_chunk_no = chunk_files[-1]
    os.chdir(Path(ROOT_TEST_PATH))
    print(f"Sync done!; latest_chunk_no: {latest_chunk_no}")

    return sync_time_seconds, latest_chunk_no, eras_start_time_dict


def date_diff_in_seconds(dt2, dt1):
    timedelta = dt2 - dt1
    return timedelta.days * 24 * 3600 + timedelta.seconds


def get_calculated_slot_no(env):
    global shelley_start_time, byron_start_time

    if env == "testnet":
        byron_start_time = datetime.strptime("2019-07-24 20:20:16", "%Y-%m-%d %H:%M:%S")
        shelley_start_time = datetime.strptime("2020-07-28 20:20:16", "%Y-%m-%d %H:%M:%S")
    elif env == "staging":
        byron_start_time = datetime.strptime("2017-09-26 18:23:33", "%Y-%m-%d %H:%M:%S")
        shelley_start_time = datetime.strptime("2020-08-01 18:23:33", "%Y-%m-%d %H:%M:%S")
    elif env == "mainnet":
        byron_start_time = datetime.strptime("2017-09-23 21:44:51", "%Y-%m-%d %H:%M:%S")
        shelley_start_time = datetime.strptime("2020-07-29 21:44:51", "%Y-%m-%d %H:%M:%S")
    elif env == "shelley_qa":
        byron_start_time = datetime.strptime("2020-08-17 13:00:00", "%Y-%m-%d %H:%M:%S")
        shelley_start_time = datetime.strptime("2020-08-17 17:00:00", "%Y-%m-%d %H:%M:%S")

    current_time = datetime.utcnow()

    latest_slot_no = int(date_diff_in_seconds(shelley_start_time, byron_start_time) / 20 +
                         date_diff_in_seconds(current_time, shelley_start_time))

    print("----------------------------------------------------------------")
    print(f"byron_start_time        : {byron_start_time}")
    print(f"shelley_start_time      : {shelley_start_time}")
    print(f"current_utc_time        : {current_time}")
    print(f"latest_slot_no          : {latest_slot_no}")
    print("----------------------------------------------------------------")

    return latest_slot_no


def main():
    start_test_time = get_current_date_time()
    print(f"Start test time:            {start_test_time}")
    global NODE
    global CLI

    secs_to_start1, secs_to_start2 = 0, 0

    set_repo_paths()

    env = vars(args)["environment"]
    print(f"env: {env}")

    set_node_socket_path_env_var()

    tag_no1 = str(vars(args)["tag_number1"]).strip()
    tag_no2 = str(vars(args)["tag_number2"]).strip()
    print(f"tag_no1: {tag_no1}")
    print(f"tag_no2: {tag_no2}")

    platform_system, platform_release, platform_version = get_os_type()
    print(f"platform: {platform_system, platform_release, platform_version}")

    if "windows" in platform_system.lower():
        NODE = "cardano-node.exe"
        CLI = "cardano-cli.exe"

    get_node_config_files_time = get_current_date_time()
    print(f"Get node config files time: {get_node_config_files_time}")
    print("get the node config files")
    get_node_config_files(env)

    get_node_build_files_time = get_current_date_time()
    print(f"Get node build files time:  {get_node_build_files_time}")
    print("get the pre-built node files")
    get_and_extract_node_files(tag_no1)

    print("===================================================================================")
    print(f"=========================== Start sync using tag_no1: {tag_no1} ==================")
    print("===================================================================================")

    print(" --- node version ---")
    cardano_cli_version1, cardano_cli_git_rev1 = get_node_version()
    print(f"  - cardano_cli_version1: {cardano_cli_version1}")
    print(f"  - cardano_cli_git_rev1: {cardano_cli_git_rev1}")

    print(f"   ======================= Start node using tag_no1: {tag_no1} ====================")
    start_sync_time1 = get_current_date_time()
    if "linux" in platform_system.lower() or "darwin" in platform_system.lower():
        secs_to_start1 = start_node_unix(env, tag_no1)
    elif "windows" in platform_system.lower():
        secs_to_start1 = start_node_windows(env, tag_no1)

    print(" - waiting for the node to sync")
    (sync_time_seconds, latest_chunk_no, eras_start_time_dict) = wait_for_node_to_sync(env, tag_no1)

    print("++++++++++++++++++++++++++++++++++++++++++++++")
    print(f"eras_start_time_dict: {eras_start_time_dict}")
    for era in eras_start_time_dict:
        print(f"{era} --> {eras_start_time_dict[era]}")
    print("++++++++++++++++++++++++++++++++++++++++++++++")

    end_sync_time1 = get_current_date_time()
    print(f"secs_to_start1            : {secs_to_start1}")
    print(f"start_sync_time1          : {start_sync_time1}")
    print(f"end_sync_time1            : {end_sync_time1}")
    # print(f"byron_sync_time_seconds1  : {byron_sync_time_seconds1}")
    # print(
    #     f"byron_sync_time1  : {time.strftime('%H:%M:%S', time.gmtime(byron_sync_time_seconds1))}"
    # )
    # print(f"shelley_sync_time_seconds1: {shelley_sync_time_seconds1}")
    # print(
    #     f"shelley_sync_time1: {time.strftime('%H:%M:%S', time.gmtime(shelley_sync_time_seconds1))}"
    # )
    # print(f"allegra_sync_time_seconds1: {allegra_sync_time_seconds1}")
    # print(
    #     f"allegra_sync_time_seconds1: {time.strftime('%H:%M:%S', time.gmtime(allegra_sync_time_seconds1))}"
    # )
    # print(f"mary_sync_time_seconds1: {mary_sync_time_seconds1}")
    # print(
    #     f"mary_sync_time_seconds1: {time.strftime('%H:%M:%S', time.gmtime(mary_sync_time_seconds1))}"
    # )

    latest_block_no1 = get_current_tip(tag_no1)[0]
    latest_slot_no1 = get_current_tip(tag_no1)[2]
    # sync_speed_bps1 = int(
    #     latest_block_no1 / (
    #             byron_sync_time_seconds1 + shelley_sync_time_seconds1 + allegra_sync_time_seconds1 + mary_sync_time_seconds1)
    # )
    # sync_speed_sps1 = int(
    #     latest_slot_no1 / (
    #             byron_sync_time_seconds1 + shelley_sync_time_seconds1 + allegra_sync_time_seconds1 + mary_sync_time_seconds1)
    # )
    # print(f"sync_speed_bps1   : {sync_speed_bps1}")
    # print(f"sync_speed_sps1   : {sync_speed_sps1}")
    #
    # total_chunks1 = int(newest_chunk1.split(".")[0])
    # print(f"downloaded chunks1: {total_chunks1}")

    (
        cardano_cli_version2,
        cardano_cli_git_rev2,
        shelley_sync_time_seconds2,
        total_chunks2,
        latest_block_no2,
        latest_slot_no2,
        start_sync_time2,
        end_sync_time2,
        start_sync_time3,
        sync_time_after_restart_seconds
    ) = (None, None, None, None, None, None, None, None, None, None)
    if tag_no2 != "None":
        print(f"   =============== Stop node using tag_no1: {tag_no1} ======================")
        stop_node()

        print("   ================ Delete the previous node files =======================")
        delete_node_files()

        print("==============================================================================")
        print(f"===================== Start sync using tag_no2: {tag_no2} ===================")
        print("==============================================================================")
        get_and_extract_node_files(tag_no2)

        print(" --- node version ---")
        cardano_cli_version2, cardano_cli_git_rev2 = get_node_version()
        print(f"  - cardano_cli_version2: {cardano_cli_version2}")
        print(f"  - cardano_cli_git_rev2: {cardano_cli_git_rev2}")
        print(f"   ================ Start node using tag_no2: {tag_no2} ====================")
        start_sync_time2 = get_current_date_time()
        if "linux" in platform_system.lower() or "darwin" in platform_system.lower():
            secs_to_start2 = start_node_unix(env, tag_no2)
        elif "windows" in platform_system.lower():
            secs_to_start2 = start_node_windows(env, tag_no2)

        start_sync2 = time.perf_counter()

        print(f" - waiting for the node to sync - using tag_no2: {tag_no2}")
        (
            newest_chunk2,
            byron_sync_time_seconds2,
            shelley_sync_time_seconds2,
            allegra_sync_time_seconds2,
            mary_sync_time_seconds2,
            sync_details_dict2
        ) = wait_for_node_to_sync(env, tag_no2)

        end_sync2 = time.perf_counter()
        end_sync_time2 = get_current_date_time()
        sync_time_after_restart_seconds = int(end_sync2 - start_sync2)

        print(f"secs_to_start2    : {secs_to_start2}   = ledger revalidation time")
        print(f"start_sync_time2  : {start_sync_time2}")
        print(f"end_sync_time2    : {end_sync_time2}")
        print(f"byron_sync_time_seconds2  : {byron_sync_time_seconds2}")
        print(f"byron_sync_time2  : "
              f"{time.strftime('%H:%M:%S', time.gmtime(byron_sync_time_seconds2))}")
        print(f"shelley_sync_time_seconds2: {shelley_sync_time_seconds2}")
        print(f"shelley_sync_time2: "
              f"{time.strftime('%H:%M:%S', time.gmtime(shelley_sync_time_seconds2))}")
        print(f"allegra_sync_time_seconds2: {allegra_sync_time_seconds2}")
        print(f"allegra_sync_time_seconds2: "
              f"{time.strftime('%H:%M:%S', time.gmtime(allegra_sync_time_seconds2))}")
        print(f"mary_sync_time_seconds2: {mary_sync_time_seconds2}")
        print(f"mary_sync_time_seconds2: "
              f"{time.strftime('%H:%M:%S', time.gmtime(mary_sync_time_seconds2))}")

        latest_block_no2 = get_current_tip(tag_no2)[0]
        latest_slot_no2 = get_current_tip(tag_no2)[2]
        sync_speed_bps2 = int(
            (latest_block_no2 - latest_block_no1)
            / (
                    byron_sync_time_seconds2 + shelley_sync_time_seconds2 + allegra_sync_time_seconds2 + mary_sync_time_seconds2)
        )
        sync_speed_sps2 = int(
            (latest_slot_no2 - latest_slot_no1)
            / (
                    byron_sync_time_seconds2 + shelley_sync_time_seconds2 + allegra_sync_time_seconds2 + mary_sync_time_seconds2)
        )
        print(f"sync_speed_bps2   : {sync_speed_bps2}")
        print(f"sync_speed_sps2   : {sync_speed_sps2}")

        # total_chunks2 = int(newest_chunk1.split(".")[0])
        print(f"downloaded chunks2: {total_chunks2}")

    chain_size = get_size(Path(ROOT_TEST_PATH) / "db")

    print("move to 'cardano_node_tests_path/scripts'")
    os.chdir(Path(ROOT_TEST_PATH) / "sync_tests")
    current_directory = Path.cwd()
    print(f" - sync_tests listdir: {os.listdir(current_directory)}")

    # test_values = (
    #     env,
    #     tag_no1,
    #     tag_no2,
    #     cardano_cli_version1,
    #     cardano_cli_version2,
    #     cardano_cli_git_rev1,
    #     cardano_cli_git_rev2,
    #     start_sync_time1,
    #     end_sync_time1,
    #     start_sync_time2,
    #     end_sync_time2,
    #     byron_sync_time_seconds1,
    #     shelley_sync_time_seconds1,
    #     allegra_sync_time_seconds1,
    #     mary_sync_time_seconds1,
    #     sync_time_after_restart_seconds,
    #     total_chunks1,
    #     total_chunks2,
    #     latest_block_no1,
    #     latest_block_no2,
    #     latest_slot_no1,
    #     latest_slot_no2,
    #     secs_to_start1,
    #     secs_to_start2,
    #     platform_system,
    #     platform_release,
    #     platform_version,
    #     chain_size,
    #     json.dumps(sync_details_dict1),
    # )

    # print(f"test_values: {test_values}")
    #
    # with open("sync_results.log", "w+") as file1:
    #     file1.write(str(test_values))
    #
    # current_directory = Path.cwd()
    # print(f" - sync_tests listdir: {os.listdir(current_directory)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Execute basic sync test\n\n")

    parser.add_argument(
        "-t1", "--tag_number1", help="tag number1 - used for initial sync, from clean state"
    )
    parser.add_argument(
        "-t2", "--tag_number2", help="tag number2 - used for final sync, from existing state"
    )
    parser.add_argument(
        "-e",
        "--environment",
        help="the environment on which to run the tests - shelley_qa, testnet, staging or mainnet.",
    )

    args = parser.parse_args()

    main()
