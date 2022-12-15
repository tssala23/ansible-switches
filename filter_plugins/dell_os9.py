import warnings

def parseRange(s):
        """
        Helper method which parses interface ranges (1/1-1/5, 1/6/1-1/6/4, etc.)

        :param s: Input range
        :type s: str
        :return: List of all interfaces in range
        :rtype: list
        """

        out = []

        s_parts = s.split(",")
        for cur in s_parts:
            if "-" in cur:
                # this is a range
                cur_parts = cur.split("-")
                first_elem_parts = cur_parts[0].split("/")
                last_elem_parts = cur_parts[1].split("/")
                part_size = len(first_elem_parts)

                index = -1
                if part_size >= 1 and first_elem_parts[0] != last_elem_parts[0]:
                    # this is unlikely
                    index = 0
                elif part_size >= 2 and first_elem_parts[1] != last_elem_parts[1]:
                    index = 1
                elif part_size >= 3 and first_elem_parts[2] != last_elem_parts[2]:
                    index = 2

                if index >= 0:
                    for x in range(first_elem_parts[index], last_elem_parts[index] + 1):
                        out_str = first_elem_parts
                        out_str[index] = x
                        out.append(out_str)
            else:
                # this is not a range
                out.append(cur)

        return out

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
        "1/1": {
            "untagged": 100
            "tagged": [101,102]
        },
        "1/2": {
            "untagged": None
            "tagged": [101,102]
        }
    }

    :param vlan_dict: VLAN dictionary set by the user
    :type vlan_dict: dict
    :param sw_config: dict of switch configuration
    :type sw_config: dict
    :returns: dict of VLANs assigned to each interface
    :rtype: dict
    """

    out = {}

    revLabelMap = os9_getLabelMap(sw_config, reverse=True)

    for vlan in vlan_dict.keys():
        intf_label = "interface Vlan " + str(vlan)
        cur_vlan_dict = sw_config[intf_label]


        for vlan_entry in cur_vlan_dict.keys():
            if vlan_entry.startswith("untagged"):
                tag_str = "untagged"
            elif vlan_entry.startswith("tagged"):
                tag_str = "tagged"
            else:
                continue

            # found untagged entry
            vlan_entry_parts = vlan_entry.split(" ")
            untag_port_type = vlan_entry_parts[1]
            untag_port_range = vlan_entry_parts[2]

            cur_portlist = parseRange(untag_port_range)

            for port in cur_portlist:
                full_swname = untag_port_type + " " + port
                conf_label = revLabelMap[full_swname]

                if conf_label not in out:
                    out[conf_label] = {}
                if "untagged" not in out[conf_label]:
                    out[conf_label]["untagged"] = []
                if "tagged" not in out[conf_label]:
                    out[conf_label]["tagged"] = []

                out[conf_label][tag_str].append(vlan)

    return out

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

    def getSpacesInStartOfString(s):
        return len(s) - len(s.lstrip())

    out = {}

    trimmed_split_conf = split_conf[index:]
    numIndex = getSpacesInStartOfString(trimmed_split_conf[0])

    lastLine = ""
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

    return lastIndex - 1,out

def os9_getFactDict(sw_facts):
    """
    Ansible filter plugin which is what starts the recursive os9_recurseLines method

    :param sw_facts: raw configuration output from switch
    :type sw_facts: str
    :return: dict of parsed switch configuration
    :rtype: dict
    """
    split_conf = sw_facts["ansible_facts"]["ansible_net_config"].splitlines()

    return os9_recurseLines(0, split_conf)[1]

def os9_getSystemConfig(sys_dict, sw_config):
    """
    Ansible filter plugin which generates the os9 commands for system config

    :param sys_dict: System configuration dict
    :type sys_dict: dict
    :param sw_config: Switch configuration dict
    :type sw_config: dict
    :return: system configuration dict
    :rtype: dict
    """

    out = {}

    num_stp_prot = 3
    stp_types = ["rstp", "mstp", "pvst"]

    for sys_field,sys in sys_dict.items():
        if sys_field == "stp":
            # make sure all other stp protocols are disabled
            stp_types.remove(sys["type"])
            if len(stp_types) < num_stp_prot - 1:
                raise ValueError("Multiple STP types cannot be specified")

            for unused_stp in stp_types:
                unused_field_name = "protocol spanning-tree " + unused_stp
                if unused_field_name in sw_config and "no disable" in sw_config[unused_field_name]:
                    out[unused_field_name] = ["disable"]

            field_name = "protocol spanning-tree " + sys["type"]
            out[field_name] = []
            if "enabled" in sys and sys["enabled"]:
                out[field_name].append("no disable")
            else:
                out[field_name].append("disable")

            if sys["type"] == "rstp":
                if "bridge-priority" in sys:
                    out[field_name].append("bridge-priority " + str(sys["bridge-priority"]))
                else:
                    out[field_name].append("no bridge-priority")

        elif sys_field == "vlt":
            # does a current VLT domain exist and is it the same?
            existing_vlt_conf = [ k for k in sw_config.keys() if k.startswith("vlt domain") ]
            for existing_conf in existing_vlt_conf:
                cur_vlt_domain = existing_conf.split(" ")[2]
                conf_domain = sys["domain"]
                if conf_domain != int(cur_vlt_domain):
                    # remove this domain
                    out["no vlt domain " + str(cur_vlt_domain)] = []

            field_name = "vlt domain " + str(sys["domain"])
            out[field_name] = []

            if "priority" in sys:
                out[field_name].append("primary-priority " + str(sys["priority"]))
            else:
                out[field_name].append("no primary-priority")

            if "peer-link" in sys:
                out[field_name].append("back-up destination " + str(sys["peer-link"]))
            else:
                out[field_name].append("no back-up destination")

            if "port-channel" in sys:
                out[field_name].append("peer-link port-channel " + str(sys["port-channel"]))
            else:
                out[field_name].append("no peer-link port-channel")

    return out

def os9_cleanupSystemConfig(sw_config):
    """
    Cleanup lasting configs from system config
    """

    out = []

    # clean up stp
    for key,value in sw_config.items():
        if key.startswith("protocol spanning-tree"):
            if "disable" in value:
                out.append("no " + key)


def os9_getFanoutConfig(intf_dict, sw_config):
    """
    Ansible filter plugin which generates the os9 commands for fanout config

    :param intf_dict: Interface configuration dict
    :type intf_dict: dict
    :param sw_config: Switch configuration dict
    :type sw_config: dict
    :return: fanout configuration dict
    :rtype: dict
    """

    # prepare label map
    label_map = os9_getLabelMap(sw_config)

    out = []

    for intf_label,intf in intf_dict.items():

        # get port number
        intf_parts = intf_label.split("/")
        port_num = intf_parts[1]

        conf_str_start = "stack-unit 1 port " + str(port_num)

        existing_fanout_conf = [ k for k in sw_config.keys() if k.startswith(conf_str_start) ]

        if len(intf_parts) > 2:
            # This is a subbport - skip
            continue

        if intf_label not in label_map and len(existing_fanout_conf) == 0:
            warnings.warn("Warning: Skipping " + intf_label + " because it was not found on the switch")
            continue

        has_fanout = "fanout" in intf and "fanout_speed" in intf
        if has_fanout:
            conf_str = conf_str_start + " portmode " + intf["fanout"] + " speed " + intf["fanout_speed"]

            if len(existing_fanout_conf) > 0:
                # fanout config already exists, revert existing config if needed
                if existing_fanout_conf[0] == conf_str:
                    # this config is already applied on the switch so we can skip this
                    # TODO this doesn't seem to fire
                    continue
                else:
                    # we need to clear the old configuration first

                    # first, set all interfaces to default state within the stack
                    for x in [ k for k in sw_config.keys() if intf_label in k and k.startswith("interface") ]:
                        # TODO this only appends the first interface?
                        out.append("default " + x)

                    existing_revert = existing_fanout_conf[0].split("speed")[0].strip()
                    out.append("no " + existing_revert + " no-confirm")
            else:
                # if the config doesn't exist, we need to default the interface being fanned out
                port_label = label_map[intf_label]
                out.append("default interface " + port_label)

            out.append(conf_str + " no-confirm")
        else:
            # fanout config doesn't exist - verify that there is nothing to revert
            if len(existing_fanout_conf) > 0:
                for x in [ k for k in sw_config.keys() if intf_label in k and k.startswith("interface") ]:
                    out.append("default " + x)

                existing_revert = existing_fanout_conf[0].split("speed")[0].strip()
                out.append("no " + existing_revert + " no-confirm")

    return out

def os9_getIntfConfig(intf_dict, sw_config, type="intf"):
    """
    Ansible filter plugin which generates the os9 commands for interface configuration

    :param intf_dict: Interface configuration dict
    :type intf_dict: dict
    :param sw_config: Switch configuration dict
    :type sw_config: dict
    :param type: Type of interface ("intf", "vlan", or "port-channel")
    :type type: str
    :return: interface configuration dict
    :rtype: dict
    """

    # prepare label map if regular interface
    label_map = os9_getLabelMap(sw_config)

    out_all = {}

    for intf_label,intf in intf_dict.items():
        # check that interface exists
        if type == "intf" and "fanout" in intf:
            # skip fanout interfaces here
            continue

        if type == "intf" and intf_label not in label_map:
            warnings.warn("Warning: Skipping " + intf_label + " because it was not found on the switch")
            continue
        elif type == "vlan" and intf_label not in intf_dict:
            warnings.warn("Warning: Skipping interface vlan " + intf_label + " because that VLAN doesn't exist")
            continue

        out = []

        if type == "intf":
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
                    range_list = parseRange(range_part)
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

        # gather current interface configuration
        cur_intf_config = sw_config["interface " + sw_label]

        # determine if interface is it L2 or L3 mode
        vlans_included = "untagged_vlan" in intf \
                                    or "tagged_vlan" in intf
        l2_exclusive_settings = "untagged_vlan" in intf \
                                    or "tagged_vlan" in intf \
                                    or "stp-edge" in intf
        l3_exclusive_settings = "ip4" in intf \
                                    or "ip6" in intf \
                                    or "keepalive" in intf

        if l2_exclusive_settings:
            # L2 mode
            if type == "vlan":
                raise ValueError("VLAN interfaces cannot operate in L2 mode")

            if any(item.startswith("ip address") for item in cur_intf_config):
                out.append("no ip address")

            if any(item.startswith("ipv6 address") for item in cur_intf_config):
                out.append("no ipv6 address")

            if vlans_included:
                if "portmode hybrid" in cur_intf_config:
                    # portmode hybrid cannot be applied while interface is in switchport mode, so we check that it's not
                    if "switchport" in cur_intf_config:
                        # TODO if the port is part of a non-default vlan, this fails!
                        out.append("no switchport")

                    out.append("portmode hybrid")
                    out.append("switchport")

            if "stp-edge" in intf and intf["stp-edge"]:
                # define edge-port for every stp protocol in os9 (only live one will take effect)
                out.append("spanning-tree rstp edge-port")
                out.append("spanning-tree mstp edge-port")
                out.append("spanning-tree pvst edge-port")
            else:
                # disable spanning tree edge port if currently enabled
                if "spanning-tree rstp edge-port" in cur_intf_config:
                    out.append("no spanning-tree rstp edge-port")

                if "spanning-tree mstp edge-port" in cur_intf_config:
                    out.append("no spanning-tree mstp edge-port")

                if "spanning-tree pvst edge-port" in cur_intf_config:
                    out.append("no spanning-tree pvst edge-port")

        elif l3_exclusive_settings:
            # L3 mode
            if "type" != "vlan":
                if "portmode hybrid" in cur_intf_config:
                    # TODO if the port is part of a non-default vlan, this fails!
                    out.append("no portmode hybrid")

                if "switchport" in cur_intf_config:
                    # TODO if the port is part of a non-default vlan, this fails!
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

        # additional confs
        if "custom" in intf:
            for add_conf in intf["custom"]:
                out.append(add_conf)

        if out:
            # output list is not empty
            out_all[sw_label] = out

    return out_all

def os9_getLACPConfig(pc_dict, sw_config):
    """
    Ansible filter plugin which generates LACP configuration commands

    :param pc_dict: Port channel dictionary
    :type pc_dict: dict
    :param sw_config: Switch configuration dict
    :type sw_config: dict
    :return: dict with nested lacp interface configuration
    :rtype: dict
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

    label_map = os9_getLabelMap(sw_config)

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
                    leftover_interfaces.delete(cur_intf)

            # revert any LACP members that aren't in the config anymore
            for cur_intf in leftover_interfaces:
                sw_label = label_map[cur_intf]

                if sw_label not in out:
                    out[sw_label] = []

                out[sw_label].append("no port-channel " + str(pc_label))

    return out

def os9_cleanupLACPConfig(intf_dict, sw_config):
    """
    After os9_getLACPConfig, some interfaces may be left with LACP active with no ports assigned, this method cleans that up.

    :param pc_dict: Port channel dictionary
    :type pc_dict: dict
    :param sw_config: Switch configuration dict
    :type sw_config: dict
    :return: dict with nested lacp interface configuration
    :rtype: dict
    """
    label_map = os9_getLabelMap(sw_config)

    out = {}

    for intf in intf_dict.keys():
        if intf not in label_map:
            warnings.warn("Warning: Skipping " + intf + " because it was not found on the switch")
            continue

        # get switch label
        sw_label = label_map[intf]

        # gather current interface configuration
        cur_intf_config = sw_config["interface " + sw_label]

        # disable port-channel-protocol if empty (since this runs AFTER lacp config)
        if "port-channel-protocol lacp" in cur_intf_config:
            if len(cur_intf_config["port-channel-protocol lacp"]) == 0:
                if sw_label not in out:
                    out[sw_label] = []

                out[sw_label].append("no port-channel-protocol lacp")

    return out


def os9_getVlanConfig(intf_dict, vlan_dict, sw_config):
    """
    Ansible filter plugin which generates the VLAN configuration commands

    :param intf_dict: Interface configuration dict
    :type intf_dict: dict
    :param vlan_dict: VLAN configuration dict
    :type vlan_dict: dict
    :param sw_config: Switch configuration dict
    :type sw_config: dict
    :return: interface configuration dict
    :rtype: dict
    """

    # prepare label map
    label_map = os9_getLabelMap(sw_config)

    out = {}

    vlanMap = os9_getVLANAssignmentMap(vlan_dict, sw_config)

    field_list = ["untagged", "tagged"]

    for intf_label,intf in intf_dict.items():

        if intf_label not in label_map:
            warnings.warn("Warning: Skipping " + intf_label + " because it was not found on the switch")
            continue

        if intf_label in vlanMap:
            existing_vlans = vlanMap[intf_label]
        else:
            existing_vlans = None

        sw_label = label_map[intf_label]

        if "untagged" in intf:
            vlan = intf["untagged"]

            if vlan not in out:
                out[vlan] = []

            if existing_vlans is not None and vlan in existing_vlans["untagged"]:
                existing_vlans["untagged"].remove(vlan)

            out[vlan].append("untagged " + str(sw_label))

        if "tagged" in intf:
            for vlan in intf["tagged"]:
                if vlan not in out:
                    out[vlan] = []

                if existing_vlans is not None and vlan in existing_vlans["tagged"]:
                    existing_vlans["tagged"].remove(vlan)

                out[vlan].append("tagged " + str(sw_label))

        # remove any old vlans no longer in config
        if existing_vlans is not None:
            for field in field_list:
                if field in existing_vlans:
                    for vlan in existing_vlans[field]:
                        out[vlan].append("no " + field + str(sw_label))

    return out

# Ansible filtermodule class
class FilterModule(object):
    def filters(self):
        return {
            "os9_getFactDict": os9_getFactDict,
            "os9_getSystemConfig": os9_getSystemConfig,
            "os9_cleanupSystemConfig": os9_cleanupSystemConfig,
            "os9_getFanoutConfig": os9_getFanoutConfig,
            "os9_getIntfConfig": os9_getIntfConfig,
            "os9_getLACPConfig": os9_getLACPConfig,
            "os9_cleanupLACPConfig": os9_cleanupLACPConfig,
            "os9_getVlanConfig": os9_getVlanConfig
        }
