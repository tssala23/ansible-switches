import warnings

# Warning helper method
def warning_on_one_line(message, category, filename, lineno, file=None, line=None):
    return '%s: %s\n' % (category.__name__, message)

warnings.formatwarning = warning_on_one_line

#
# Helper methods
#
def os9_parseRange(s, sw_config):
    def remove_trailing_zeros(value):
        parts = value.split("/")
        while parts and parts[-1] == "0":
            parts.pop()
        return "/".join(parts)

    def normalize_length(intf):
        return intf + "/0" * (2 - intf.count("/"))

    def increment_parts(parts):
        return [str(int(part) + 1) for part in parts]

    def generate_check_list(intf_parts, iterate_parts):
        return [
            "/".join([intf_parts[0], intf_parts[1], iterate_parts[2]]),
            "/".join([intf_parts[0], iterate_parts[1], "0"]),
            "/".join([intf_parts[0], iterate_parts[1], "1"]),
            "/".join([iterate_parts[0], "0", "0"]),
            "/".join([iterate_parts[0], "0", "1"]),
            "/".join([iterate_parts[0], "1", "0"]),
            "/".join([iterate_parts[0], "1", "1"]),
        ]

    def iterate_intf(intf, sw_keys):
        intf = normalize_length(intf)
        intf_parts = intf.split("/")
        iterate_parts = increment_parts(intf_parts)
        check_list = generate_check_list(intf_parts, iterate_parts)

        for item in check_list:
            if item in sw_keys:
                return remove_trailing_zeros(item)
        return None

    sw_keys = [normalize_length(key.split()[-1]) for key in sw_config if key.startswith("interface") and not key.startswith("interface Vlan")]
    out = []

    s_parts = s.split(",")

    for s_cur in s_parts:
        if "-" in s_cur:
            range_parts = s_cur.split("-")
            cur_part = range_parts[0]

            while cur_part != range_parts[1]:
                out.append(cur_part)
                cur_part = iterate_intf(cur_part, sw_keys)
            out.append(range_parts[1])
        else:
            out.append(s_cur)

    return out

def combineTuples(list1, list2):
    """
    Helper method which combines two lists of tuples, removing duplicates

    :param list1: First list (first in order of ops)
    :type list1: list
    :param list2: Second list (second in order of ops)
    :type list2: list
    :return: Combined list with duplicates removed
    :rtype: list
    """

    out = []

    removeList = []

    for i in list1:
        search_key = i[0]
        found = False

        for j in list2:
            if j[0] == search_key:
                # found duplicate
                found = True
                out.append((i[0], i[1] + j[1]))
                removeList.append(j)
                break

        if not found:
            out.append(i)

    for r in removeList:
        # remove duplicates here
        list2.remove(r)

    out += list2

    return out

#
# Map methods
#
def os9_getFactDict(sw_facts):
    """
    Method which converts the switch facts gathered by ansible into a more python-usable dict

    :param sw_facts: raw configuration output from switch
    :type sw_facts: str
    :return: dict of parsed switch configuration
    :rtype: dict
    """

    def getSpacesInStartOfString(s):
        return len(s) - len(s.lstrip())

    def os9_recurseLines(index, split_conf):
        """
        Recurseive method which takes a nested configuration from a dell switch and converts it into a usable dict

        :param index: Index to begin recursing through
        :type index: int
        :param split_conf: List of lines from raw switch output configuration
        :type split_conf: list
        :return: dict of parsed switch configuration
        :rtype: dict
        """

        out = {}

        trimmed_split_conf = split_conf[index:]
        numIndex = getSpacesInStartOfString(trimmed_split_conf[0])

        lastLine = ""
        lastIndex = 0
        skipint = 0
        for i, line in enumerate(trimmed_split_conf):
            if skipint > 0:
                skipint -= 1
                continue

            if "!" in line:
                continue

            cur_numSpaces = getSpacesInStartOfString(line)

            # remove whitespace after counting
            line = line.strip()

            if cur_numSpaces < numIndex:
                # we're done with this section
                return i - 1,out

            if cur_numSpaces == numIndex:
                # we can add this directly
                out[line] = {}

            if cur_numSpaces > numIndex:
                # start a new recursion
                rec_line = os9_recurseLines(i, trimmed_split_conf)

                out[lastLine] = rec_line[1]
                skipint = rec_line[0]  # skip the lines that were covered by the recursion

            lastLine = line
            lastIndex = i

        return lastIndex - 1, out

    split_conf = sw_facts["ansible_facts"]["ansible_net_config"].splitlines()

    return os9_recurseLines(0, split_conf)[1]

def os9_getLabelMap(sw_config, reverse=False):
    """
    Creates a dictionary with a label map which looks something like this:

    {
        "1/1": "tengigabitethernet 1/1",
        "1/54": "hundredgigabitethernet 1/54"
        ...
    }

    :param sw_config: dictionary of switch configuration
    :type sw_config: dict
    :param reverse: return the reverse lookup dict
    :type reverse: bool
    :returns: Dictionary of interface label map
    :rtype: dict
    """

    label_map = {}

    # don't include these interface types in the label map
    intf_blacklist = [
        "ManagementEthernet",
        "vlan",
        "port-channel",
        "group",
        "loopback",
        "null",
        "tunnel"
    ]

    intf_conf = [ i for i in sw_config if i.startswith('interface') and not any(y in i for y in intf_blacklist) ]

    for intf in intf_conf:
        intf_parts = intf.split(" ")

        sw_label = " ".join(intf_parts[1:3])
        conf_label = intf_parts[2]

        if reverse:
            label_map[sw_label] = conf_label
        else:
            label_map[conf_label] = sw_label

    return label_map

def os9_getVLANAssignmentMap(vlan_dict, sw_config):
    """
    Creates a dictionary where the keys are interfaces, such as:

    {
        "TenGigabitEthernet 1/1": {
            "untagged": 100
            "tagged": [101,102]
        },
        "TenGigabitEthernet 1/2": {
            "untagged": None
            "tagged": [101,102]
        }
    }

    :param vlan_dict: VLAN dictionary set by the user
    :type vlan_dict: dict
    :param sw_config: dict of switch configuration
    :type sw_config: dict
    :param revLabelMap: Reverse label map of interfaces
    :type revLabelMap: dict
    :returns: dict of VLANs assigned to each interface
    :rtype: dict
    """

    out = {}

    for vlan in vlan_dict.keys():
        intf_label = "interface Vlan " + str(vlan)

        if intf_label in sw_config:
            cur_vlan_dict = sw_config[intf_label]
        else:
            cur_vlan_dict = {}

        for vlan_entry in cur_vlan_dict.keys():
            if vlan_entry.startswith("untagged"):
                tag_str = "untagged"
            elif vlan_entry.startswith("tagged"):
                tag_str = "tagged"
            else:
                continue

            # found untagged entry
            vlan_entry_parts = vlan_entry.split(" ")
            port_type = vlan_entry_parts[1]
            port_range = vlan_entry_parts[2]

            cur_portlist = os9_parseRange(port_range, sw_config)

            for port in cur_portlist:
                full_swname = port_type + " " + str(port)

                if full_swname not in out:
                    out[full_swname] = {}
                if "untagged" not in out[full_swname]:
                    out[full_swname]["untagged"] = []
                if "tagged" not in out[full_swname]:
                    out[full_swname]["tagged"] = []

                out[full_swname][tag_str].append(vlan)

    return out

#
# Config generators
#
def os9_getFanoutConfig(intf_dict, sw_config, label_map):
    """
    Gets the os9 commands for fanout port configurations

    :param intf_dict: Interface configuration dict
    :type intf_dict: dict
    :param sw_config: Switch configuration dict
    :type sw_config: dict
    :param label_map: Label map for interfaces
    :type label_map: dict
    :return: List of tuples for fanout configuration
    :rtype: list
    """

    def getInterfaceChildren(port_num, label_map):
        out = []

        checkStr = ["1", str(port_num), "1"]
        while "/".join(checkStr) in label_map:
            out.append(label_map["/".join(checkStr)])

            checkStr[2] = str(int(checkStr[2]) + 1)

        return out

    out_tuple = []
    out = []

    for intf_label,intf in intf_dict.items():

        # get port number
        intf_parts = intf_label.split("/")
        port_num = intf_parts[1]

        conf_str_start = "stack-unit 1 port " + str(port_num)

        existing_fanout_conf = [ k for k in sw_config.keys() if k.split("portmode")[0].strip() == conf_str_start ]

        if len(intf_parts) > 2:
            # This is a subbport - skip
            continue

        has_fanout = "fanout" in intf and "fanout_speed" in intf
        if has_fanout:
            conf_str = conf_str_start + " portmode " + intf["fanout"]
            conf_str_speed = conf_str + " speed " + intf["fanout_speed"]

            if len(existing_fanout_conf) > 0:
                # fanout config already exists, revert existing config if needed
                check_norm = "speed" not in existing_fanout_conf[0] and conf_str == existing_fanout_conf[0]
                check_speed = conf_str_speed == existing_fanout_conf[0]
                if check_norm or check_speed:
                    # this config is already applied on the switch so we can skip this
                    continue
                else:
                    # we need to clear the old configuration first

                    # first, set all interfaces to default state within the stack
                    for child in getInterfaceChildren(port_num, label_map):
                        out.append("default interface " + child)

                    existing_revert = existing_fanout_conf[0].split("speed")[0].strip()
                    out.append("no " + existing_revert + " no-confirm")
            else:
                # if the config doesn't exist, we need to default the interface being fanned out
                port_label = label_map[intf_label]
                out.append("default interface " + port_label)

            out.append(conf_str_speed + " no-confirm")
        else:
            # fanout config doesn't exist - verify that there is nothing to revert
            if len(existing_fanout_conf) > 0:

                for child in getInterfaceChildren(port_num, label_map):
                    out.append("default interface " + child)

                existing_revert = existing_fanout_conf[0].split("speed")[0].strip()
                out.append("no " + existing_revert + " no-confirm")

    out_tuple = [([], s) for s in out]
    return out_tuple

def os9_getIntfConfig(intf_dict, sw_config, label_map, vlan_map, type):
    """
    Generates os9 commands for interface configuration

    :param intf_dict: Interface configuration dict
    :type intf_dict: dict
    :param sw_config: Switch configuration dict
    :type sw_config: dict
    :param label_map: Label map of interfaces
    :type label_map: dict
    :param type: Type of interface ("intf", "vlan", or "port-channel")
    :type type: str
    :return: List of tuples for interface commands
    :rtype: list
    """

    out_all = []

    for intf_label,intf in intf_dict.items():
        # check that interface exists
        if type == "intf" and "fanout" in intf:
            # skip fanout interfaces here
            continue

        out = []
        reset_cmd = ""

        if type == "intf":
            if intf_label not in label_map:
                warnings.warn("Skipping interface " + intf_label + " because it does not exist.")
                continue

            sw_label = label_map[intf_label]
        elif type == "vlan":
            sw_label = "Vlan " + str(intf_label)
        elif type == "port-channel":
            sw_label = "Port-channel " + str(intf_label)

            if intf["mode"] == "normal":
                # remove any channel interfaces that need to be removed
                existing_conf = [ k for k in sw_config[sw_label].keys() if k.startswith("channel-member") ]
                for channel_line in existing_conf:
                    range_part = channel_line.split(" ")[2]
                    range_list = os9_parseRange(range_part)
                    diff_list = list(set(range_list) - set(intf["interfaces"]))

                    for removed_intf in diff_list:
                        out.append("no channel-member " + label_map[removed_intf])

                # add channel members
                for channel_intf in intf["interfaces"]:
                    out.append("channel-member " + label_map[channel_intf])
            elif intf["mode"] == "lacp":
                if "lacp_rate" in intf:
                    if intf["lacp_rate"] == "fast":
                        out.append("lacp fast-switchover")
                    else:
                        out.append("no lacp fast-switchover")
        else:
            raise ValueError("Type not set to a valid value")

        # gather current interface configuration
        if "interface" + sw_label in sw_config:
            cur_intf_config = sw_config["interface " + sw_label]
        else:
            cur_intf_config = {
                "no ip address": {},
                "no shutdown": {}
            }

        # ! TODO - we need a 3rd option for managed l2 which doesn't enforce l2 mode (ESI)

        # determine if interface is it L2 or L3 mode
        managed_l2 = "managed-l2" in intf and intf["managed-l2"]
        vlans_included = "untagged" in intf \
                                    or "tagged" in intf \
                                    or managed_l2
        hybrid_port = ("untagged" in intf \
                                    and "tagged" in intf) \
                                    or managed_l2
        l2_exclusive_settings = "untagged" in intf \
                                    or "tagged" in intf \
                                    or "stp-edge" in intf \
                                    or "managed-l2" in intf
        l3_exclusive_settings = "ip4" in intf \
                                    or "ip6" in intf \
                                    or "keepalive" in intf

        switching_modes = False

        if l2_exclusive_settings:
            # L2 mode
            if type == "vlan":
                raise ValueError("VLAN interfaces cannot operate in L2 mode")

            if any(item.startswith("ip address") for item in cur_intf_config):
                out.append("no ip address")

            if any(item.startswith("ipv6 address") for item in cur_intf_config):
                out.append("no ipv6 address")

            if vlans_included:
                if hybrid_port:
                    # portmode hybrid cannot apply if port is already in L2 mode
                    if "switchport" in cur_intf_config and "portmode hybrid" not in cur_intf_config:
                        switching_modes = True
                        out.append("no switchport")

                    out.append("portmode hybrid")

                out.append("switchport")

        elif l3_exclusive_settings:
            # L3 mode
            if "type" != "vlan":
                if "portmode hybrid" in cur_intf_config:
                    switching_modes = True
                    out.append("no portmode hybrid")

                if "switchport" in cur_intf_config:
                    switching_modes = True
                    out.append("no switchport")

            if "ip4" in intf:
                out.append("ip address " + intf["ip4"])
            else:
                if any(item.startswith("ip address") for item in cur_intf_config):
                    out.append("no ip address")

            if "ip6" in intf:
                out.append("ipv6 address " + intf["ip6"])
            else:
                if any(item.startswith("ipv6 address") for item in cur_intf_config):
                    out.append("no ipv6 address")

            if "keepalive" in intf:
                # keepalive being ON is the default
                if intf["keepalive"]:
                    if "no keepalive" in cur_intf_config:
                        out.append("keepalive")
                else:
                    out.append("no keepalive")

        if switching_modes:
            # we need to remove this interface from any non-default vlan before continuing
            # the interface will be readded in the VLAN section. This will result in a few
            # seconds of interface downtime
            reset_cmd = "default interface " + sw_label

        # set description
        if "description" in intf:
            out.append("description " + intf["description"])
        else:
            if any(item.startswith("description") for item in cur_intf_config):
                out.append("no description")

        # set admin state
        if "admin" in intf:
            if intf["admin"] == "up":
                out.append("no shutdown")
            elif intf["admin"] == "down":
                out.append("shutdown")

        if "mtu" in intf:
            out.append("mtu " + str(intf["mtu"]))
        else:
            if any(item.startswith("mtu") for item in cur_intf_config):
                out.append("no mtu")

        # STP edge port
        if "stp-edge" in intf and intf["stp-edge"]:
            out.append("spanning-tree mstp edge-port")
            out.append("spanning-tree rstp edge-port")
            out.append("spanning-tree pvst edge-port")

        # additional confs
        if "custom" in intf:
            for add_conf in intf["custom"]:
                out.append(add_conf)

        if out:
            # output list is not empty
            if reset_cmd != "":
                out_all.append(([], reset_cmd))

            out_all.append((["interface " + sw_label], out))

    return out_all

def os9_getLACPConfig(pc_dict, sw_config, label_map):
    """
    Ansible filter plugin which generates LACP configuration commands

    :param pc_dict: Port channel dictionary
    :type pc_dict: dict
    :param sw_config: Switch configuration dict
    :type sw_config: dict
    :param label_map: Label map of interfaces
    :type label_map: dict
    :return: List of tuples for LACP commands
    :rtype: list
    """

    # get a map of current LACP members (used to revert later)
    lacpmembers = {}

    for cur_intf in [ k for k in sw_config.keys() if k.startswith("interface") ]:
        # loop through every interface
        if "port-channel-protocol lacp" in sw_config[cur_intf]:
            channel_member_list = sw_config[cur_intf]["port-channel-protocol lacp"].keys()
            pc_id = channel_member_list[0].split(" ")[1]
            intf_id = cur_intf.split(" ")[2]

            if pc_id not in lacpmembers:
                lacpmembers[pc_id] = []

            lacpmembers[pc_id].append(intf_id)

    out = {}

    for pc_label,pc in pc_dict.items():
        if pc["mode"] != "lacp":
            continue

        if "interfaces" in pc:
            if str(pc_label) in lacpmembers:
                leftover_interfaces = lacpmembers[str(pc_label)]
            else:
                leftover_interfaces = []

            for cur_intf in pc["interfaces"]:
                sw_label = label_map[cur_intf]

                if sw_label not in out:
                    out[sw_label] = []

                conf_line = "port-channel " + str(pc_label) + " mode active"
                out[sw_label].append(conf_line)

                if conf_line in leftover_interfaces:
                    leftover_interfaces.remove(cur_intf)

            # revert any LACP members that aren't in the config anymore
            for cur_intf in leftover_interfaces:
                sw_label = label_map[cur_intf]

                if sw_label not in out:
                    out[sw_label] = []

                out[sw_label].append("no port-channel " + str(pc_label))

    out_all = []
    for cur_intf in out:
        # ! TODO - this seems to report as "changed" regardless
        out_all.append((["interface " + cur_intf, "port-channel-protocol lacp"], out[cur_intf]))

    return out_all

def os9_getVlanConfig(intf_dict, label_map, vlan_map, vlan_names):
    """
    Generates the VLAN configuration commands

    :param intf_dict: Interface configuration dict
    :type intf_dict: dict
    :param label_map: Interface label map
    :type label_map: dict
    :param vlan_map: VLAN configuration dict
    :type vlan_map: dict
    :param vlan_names: VLAN global configuration with names
    :type vlan_names: dict
    :param sw_config: Switch configuration dict
    :type sw_config: dict
    :return: List of tuples for vlan config
    :rtype: list
    """

    assignments = {}

    field_list = ["untagged", "tagged"]

    for intf_label,intf in intf_dict.items():

        if "fanout" in intf:
            # skip fanout interfaces here
            continue

        if intf_label not in label_map:
            warnings.warn("Skipping assigning VLANs to " + intf_label + " because the interface doesn't exist")
            continue

        sw_label = label_map[intf_label]

        if sw_label in vlan_map:
            existing_vlans = vlan_map[sw_label]
        else:
            existing_vlans = None

        if "untagged" in intf:
            vlan = intf["untagged"]

            if vlan not in assignments:
                assignments[vlan] = []

            if existing_vlans is not None and vlan in existing_vlans["untagged"]:
                existing_vlans["untagged"].remove(vlan)

            assignments[vlan].append("untagged " + str(sw_label))

        if "tagged" in intf:
            if intf["tagged"] == "all":
                # all vlans on the switch should be tagged
                vlan_list = vlan_names
            else:
                vlan_list = intf["tagged"]

            for vlan in vlan_list:
                if vlan not in assignments:
                    assignments[vlan] = []

                if existing_vlans is not None and vlan in existing_vlans["tagged"]:
                    existing_vlans["tagged"].remove(vlan)

                assignments[vlan].append("tagged " + str(sw_label))

        # remove any old vlans no longer in config
        if existing_vlans is not None:
            for field in field_list:
                if field in existing_vlans:
                    for vlan in existing_vlans[field]:
                        if vlan not in assignments:
                            assignments[vlan] = []

                        assignments[vlan].append("no " + field + str(sw_label))

    out_tuple = []

    for vlan in vlan_names:
        if int(vlan) == 1:
            # skip default vlan
            continue

        out = []

        out.append("name " + vlan_names[vlan]["name"])
        out.append("description " + vlan_names[vlan]["description"])

        if vlan in assignments:
            out += assignments[vlan]

        out_tuple.append((["interface Vlan " + str(vlan)], out))

    return out_tuple

#
# Main compilation method
#
def os9_getFanoutConfiguration(sw_facts, intf_dict):
    # first, convert the switch configuration to a dict
    sw_config = os9_getFactDict(sw_facts)

    # Based on current configuration, generate various maps
    label_map = os9_getLabelMap(sw_config)

    # Figure out the interface fanout configuration
    fanout_cfg = os9_getFanoutConfig(intf_dict, sw_config, label_map)

    return fanout_cfg

def os9_getConfiguration(sw_facts, intf_dict, vlan_dict, po_dict, vlan_names):
    """
    Main ansible filter plugin which gets called. The result of the filter is a list of tuples:

    [
        (
            ["parent commands"],
            ["cmd lines"]
        ),
        ...
    ]

    :param sw_facts: Raw ansible facts gathered from switch
    :type sw_facts: str
    :param intf_dict: Configuration dict for interfaces
    :type intf_dict: dict
    :param vlan_dict: Configuration dict for vlan interfaces
    :type vlan_dict: dict
    :param po_dict: Configuration dict for port channel interfaces
    :type po_dict: dict
    :param vlan_names: Global config for vlans
    :type vlan_names: dict
    :return: list of tuples for switch configuration
    :rtype: list
    """

    # out is a list of tuples, where each tuple's first value is the parents list
    # and the second value is the lines list
    out = []

    # first, convert the switch configuration to a dict
    sw_config = os9_getFactDict(sw_facts)

    # Based on current configuration, generate various maps
    label_map = os9_getLabelMap(sw_config)
    vlan_map = os9_getVLANAssignmentMap(vlan_names, sw_config)

    # set interface configuration
    if intf_dict is not None:
        # Update interface configuration
        intf_cfg = os9_getIntfConfig(intf_dict, sw_config, label_map, vlan_map, type = "intf")
        out += intf_cfg

    # Update port channel interface configuration
    if po_dict is not None:
        po_cfg = os9_getIntfConfig(po_dict, sw_config, label_map, vlan_map, type = "port-channel")
        out += po_cfg

        lacp_cfg = os9_getLACPConfig(po_dict, sw_config, label_map)
        out += lacp_cfg

    # Create/update vlan interfaces
    if intf_dict is not None:
        vlan_cfg = os9_getVlanConfig(intf_dict, label_map, vlan_map, vlan_names)
    else:
        vlan_cfg = []

    if vlan_dict is not None:
        vlan_intf_cfg = os9_getIntfConfig(vlan_dict, sw_config, label_map, vlan_map, type = "vlan")
    else:
        vlan_intf_cfg = []

    merged_vlan_conf = combineTuples(vlan_cfg, vlan_intf_cfg)
    out += merged_vlan_conf

    return out

# This class is required for ansible to find the filter plugins
class FilterModule(object):
    def filters(self):
        return {
            "os9_getConfiguration": os9_getConfiguration,
            "os9_getFanoutConfiguration": os9_getFanoutConfiguration
        }
