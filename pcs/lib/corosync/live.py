import os.path
import re

from pcs import settings
from pcs.common.tools import join_multilines
from pcs.lib import reports
from pcs.lib.errors import LibraryError

def get_local_corosync_conf():
    """
    Read corosync.conf file from local machine
    """
    path = settings.corosync_conf_file
    try:
        return open(path).read()
    except EnvironmentError as e:
        raise LibraryError(reports.corosync_config_read_error(path, e.strerror))


def get_local_cluster_conf():
    """
    Read cluster.conf file from local machine
    """
    path = settings.cluster_conf_file
    try:
        return open(path).read()
    except EnvironmentError as e:
        raise LibraryError(reports.cluster_conf_read_error(path, e.strerror))


def exists_local_corosync_conf():
    return os.path.exists(settings.corosync_conf_file)

def reload_config(runner):
    """
    Ask corosync to reload its configuration
    """
    stdout, stderr, retval = runner.run([
        os.path.join(settings.corosync_binaries, "corosync-cfgtool"),
        "-R"
    ])
    message = join_multilines([stderr, stdout])
    if retval != 0 or "invalid option" in message:
        raise LibraryError(reports.corosync_config_reload_error(message))

def get_quorum_status_text(runner):
    """
    Get runtime quorum status from the local node
    """
    stdout, stderr, retval = runner.run([
        os.path.join(settings.corosync_binaries, "corosync-quorumtool"),
        "-p"
    ])
    # retval is 0 on success if node is not in partition with quorum
    # retval is 1 on error OR on success if node has quorum
    if retval not in [0, 1] or stderr.strip():
        raise QuorumStatusReadException(stderr)
    return stdout

def set_expected_votes(runner, votes):
    """
    set expected votes in live cluster to specified value
    """
    stdout, stderr, retval = runner.run([
        os.path.join(settings.corosync_binaries, "corosync-quorumtool"),
        # format votes to handle the case where they are int
        "-e", "{0}".format(votes)
    ])
    if retval != 0:
        raise LibraryError(
            reports.corosync_quorum_set_expected_votes_error(stderr)
        )
    return stdout


class QuorumStatusException(Exception):
    def __init__(self, reason=""):
        super().__init__()
        self.reason = reason


class QuorumStatusReadException(QuorumStatusException):
    pass


class QuorumStatusParsingException(QuorumStatusException):
    pass


class QuorumStatus(object):
    # TODO: doctext and replace utils.parse_quorumtool_output
    # TODO: deprecate or replace old functions in utils
    # TODO: tests
    def __init__(self, data):
        self._data = data

    @classmethod
    def from_string(cls, quorum_status):
        parsed = {}
        in_node_list = False
        try:
            for line in quorum_status.splitlines():
                line = line.strip()
                if not line:
                    continue
                if in_node_list:
                    if line.startswith("-") or line.startswith("Nodeid"):
                        # skip headers
                        continue
                    parts = line.split()
                    if parts[0] == "0":
                        # this line has nodeid == 0, this is a qdevice line
                        parsed["qdevice_list"].append({
                            "name": parts[2],
                            "votes": int(parts[1]),
                            "local": False,
                        })
                    else:
                        # this line has non-zero nodeid, this is a node line
                        parsed["node_list"].append({
                            "name": parts[3],
                            "votes": int(parts[1]),
                            "local": len(parts) > 4 and parts[4] == "(local)",
                        })
                else:
                    if line == "Membership information":
                        in_node_list = True
                        parsed["node_list"] = []
                        parsed["qdevice_list"] = []
                        continue
                    if not ":" in line:
                        continue
                    parts = [x.strip() for x in line.split(":", 1)]
                    if parts[0] == "Quorate":
                        parsed["quorate"] = parts[1].lower() == "yes"
                    elif parts[0] == "Quorum":
                        match = re.match("(\d+).*", parts[1])
                        if match:
                            parsed["quorum"] = int(match.group(1))
                        else:
                            raise QuorumStatusParsingException()
        except (ValueError, IndexError):
            raise QuorumStatusParsingException()
        for required in ("quorum", "quorate", "node_list"):
            if required not in parsed:
                raise QuorumStatusParsingException(
                    f"Required section '{required}' is missing"
                )
        return cls(parsed)

    @property
    def is_quorate(self):
        return bool(self._data["quorate"])

    @property
    def votes_needed_for_quorum(self):
        return self._data["quorum"]

    @property
    def qdevice_votes(self):
        qdevice_votes = 0
        for qdevice_info in self._data.get("qdevice_list", []):
            qdevice_votes += qdevice_info["votes"]
        return qdevice_votes

    def get_votes_excluding_nodes(self, node_list):
        # TODO doctext + node_list is actually node_name_list
        votes = 0
        for node_info in self._data["node_list"]:
            if not (node_list and node_info["name"] in node_list):
                votes += node_info["votes"]
        votes += self.qdevice_votes
        return votes

    def stopping_nodes_cause_quorum_loss(self, node_list):
        # TODO doctext + node_list is actually node_name_list
        if not self.is_quorate:
            return False
        return (
            self.get_votes_excluding_nodes(node_list)
            <
            self.votes_needed_for_quorum
        )

    #def stopping_local_node_cause_quorum_loss(self):
    #    pass
    # will be implemented later when needed for the 'cluster stop' command
