from pprint import pprint

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

def os9_extendConfigDict(sw_config):
    """
    Methods which extends all the range (-) parts of the switch config into individual lines
    """
    def parseRange(s, sw_config):
        """
        Method which parses a range of interfaces into a list of interfaces
        param s: String to parse
        type s: str
        param sw_config: Switch configuration
        type sw_config: dict
        return: List of interfaces
        rtype: list
        """
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

    def handleLines(lines, prefix_list, sw_config):
        out = {}

        for line in lines:
            if any(line.startswith(prefix) for prefix in prefix_list):
                line_parts = line.split(" ")
                line_prefix = " ".join(line_parts[0:2])
                line_elements = line_parts[2]

                range_items = parseRange(line_elements, sw_config)
                for item in range_items:
                    os9_line = f"{line_prefix} {item}"
                    out[os9_line] = {}
            else:
                out[line] = {}

        return out

    out = {}

    for name,fields in sw_config.items():
        if name.startswith("interface ManagementEthernet"): continue  # Skip managementethernet
        if name == "interface Vlan 1": continue  # Skip default vlan

        if name.startswith("interface Vlan"):
            out[name] = handleLines(fields.keys(), ["untagged", "tagged"], sw_config)
        elif name.startswith("interface Port-channel"):
            out[name] = handleLines(fields.keys(), ["channel-member"], sw_config)
        elif name.startswith("interface"):
            out[name] = fields
        elif name.startswith("stack-unit 1 port"):
            out[name] = fields

    return out

def os9_convertNames(sw_config, intf_dict, vlan_dict, po_dict, vlan_names):
    def GetIntfClass(name):
        intf_conf = [ i.split(" ") for i in sw_config if name in i.split(" ") ]

        if len(intf_conf) == 0:
            # Interface not found - could be a fanout interface that doesn't exist yet
            return f"<UNKNOWNTYPE> {name}"

        return f"{intf_conf[0][1]} {name}"

    out = {}

    # Process Interface Manifest
    if intf_dict is not None:
        for intf in intf_dict.keys():
            if "fanout" in intf_dict[intf]:
                # Don't include fanout interfaces
                continue

            os9_name = GetIntfClass(intf)
            out[os9_name] = intf_dict[intf]

            # convert vlans
            if "untagged" in intf_dict[intf]:
                out[os9_name]["untagged"] = f"Vlan {intf_dict[intf]['untagged']}"

            if "tagged" in intf_dict[intf]:
                out[os9_name]["tagged"] = []
                for tagged_vlan in intf_dict[intf]["tagged"]:
                    out[os9_name]["tagged"].append(f"Vlan {tagged_vlan}")

    # Process VLAN Interface Manifest
    if vlan_names is not None:
        for vlan in vlan_names.keys():
            os9_name = f"Vlan {vlan}"
            out[os9_name] = vlan_names[vlan]

    if vlan_dict is not None:
        for vlan_intf in vlan_dict.keys():
            os9_name = f"Vlan {vlan_intf}"

            if os9_name not in out:
                print(f"Warning: VLAN interface {vlan_intf} does not have a corresponding VLAN description")
                continue

            out[os9_name] = vlan_dict[vlan_intf]

    # Process Port Channel Interface Manifest
    if po_dict is not None:
        for po_intf in po_dict.keys():
            os9_name = f"Port-channel {po_intf}"
            os9_member_names = [ GetIntfClass(i) for i in po_dict[po_intf]["interfaces"] ]
            out[os9_name] = po_dict[po_intf]
            out[os9_name]["interfaces"] = os9_member_names

    return out

def os9_generateConfig(manifest):
    """
    Method which converts the config manifests to configuration readable by dell os9
    """

    # Interface Handlers
    def ProcessDescription(name, fields, out = {}):
        if "description" not in fields: return out

        os9_line = f"description {fields['description']}"
        out[name][os9_line] = {}

        return out

    def ProcessState(name, fields, out = {}):
        prefix = ""
        if "state" in fields and fields["state"] == "up": prefix = "no "

        os9_line = f"{prefix}shutdown"
        out[name][os9_line] = {}

        return out

    def ProcessMTU(name, fields, out = {}):
        if "mtu" not in fields: return out

        os9_line = f"mtu {fields['mtu']}"
        out[name][os9_line] = {}

        return out

    def ProcessCustom(name, fields, out = {}):
        if "custom" not in fields: return out

        for line in fields["custom"]:
            out[name][line] = {}

        return out

    def ProcessPortmode(name, fields, out = {}):
        if "portmode" not in fields: return out

        if fields["portmode"] == "access" \
            or fields["portmode"] == "trunk" \
            or fields["portmode"] == "hybrid":
            out[name]["switchport"] = {}

        if fields["portmode"] == "hybrid":
            out[name]["portmode hybrid"] = {}

        return out

    def ProcessUntagged(name, fields, out = {}):
        if "untagged" not in fields: return out

        vlan = fields["untagged"]

        if vlan not in out: out[vlan] = {}

        os9_line = f"untagged {name}"
        out[vlan][os9_line] = {}

        return out

    def ProcessTagged(name, fields, out = {}):
        if "tagged" not in fields: return out

        vlan_list = fields["tagged"]

        for vlan in vlan_list:
            os9_vlan_name = f"Vlan {vlan}"
            if os9_vlan_name not in out: out[os9_vlan_name] = {}

            os9_line = f"tagged {name}"
            out[os9_vlan_name][os9_line] = {}

        return out

    def ProcessIP4(name, fields, out = {}):
        if "ip4" in fields:
            os9_line = f"ip address {fields['ip4']}"
        else:
            os9_line = "no ip address"

        out[name][os9_line] = {}

        return out

    def ProcessIP6(name, fields, out = {}):
        if "ip6" not in fields: return out

        os9_line = f"ipv6 address {fields['ip6']}"
        out[name][os9_line] = {}

        return out

    # Port Channel Handlers
    def ProcessLACPRate(name, fields, out = {}):
        if "lacp-rate" not in fields: return out

        prefix = ""
        if fields["lacp-rate"] == "slow": prefix = "no "

        os9_line = f"{prefix}lacp fast-switchover"
        out[name][os9_line] = {}

        return out

    def ProcessLAGInterfaces(name, fields, out = {}):
        if "interfaces" not in fields: return out
        if "mode" not in fields: return out

        for intf in fields["interfaces"]:
            if fields["mode"] == "normal":
                os9_line = f"channel-member {intf}"
                out[name][os9_line] = {}
            elif fields["mode"] == "lacp":
                if intf not in out: out[intf] = {}
                if "port-channel-protocol LACP" not in out[intf]: out[intf]["port-channel-protocol LACP"] = {}

                os9_line = f"{name.lower()} mode active"
                out[intf]["port-channel-protocol LACP"][os9_line] = {}

        return out

    # VLAN name handlers
    def ProcessName(name, fields, out = {}):
        if "name" not in fields: return out

        os9_line = f"name {fields['name']}"
        out[name][os9_line] = {}

        return out

    out = {}

    for name,fields in manifest.items():
        if name not in out: out[name] = {}

        out = ProcessName(name, fields, out)
        out = ProcessDescription(name, fields, out)
        out = ProcessState(name, fields, out)
        out = ProcessMTU(name, fields, out)
        out = ProcessCustom(name, fields, out)
        out = ProcessPortmode(name, fields, out)
        out = ProcessUntagged(name, fields, out)
        out = ProcessTagged(name, fields, out)
        out = ProcessIP4(name, fields, out)
        out = ProcessIP6(name, fields, out)
        out = ProcessLAGInterfaces(name, fields, out)
        out = ProcessLACPRate(name, fields, out)

    # Prefix interface in dictionary to match the os9 config
    out = {"interface " + key: value for key, value in out.items()}

    return out

def os9_manifestToAnsible(manifest):
    def traverseLeaves(d, path = [], out = []):
        if not isinstance(d, dict) or not d:
            out.append((path[:-1], path[-1]))
        else:
            for k, v in d.items():
                if k.startswith("stack-unit"): k = k + " no-confirm"

                traverseLeaves(v, path + [k])

        return out

    if len(manifest) > 0:
        out_list = traverseLeaves(manifest)
    else:
        out_list = []

    out_list.sort(key=lambda x: x[0][0].startswith("interface Vlan") if len(x[0]) > 0 else False)

    return out_list

def os9_getSwConfigDict(sw_facts):
    sw_config = os9_getFactDict(sw_facts)
    sw_config = os9_extendConfigDict(sw_config)

    return sw_config

def os9_getConfigDict(sw_facts, intf_dict, vlan_dict, po_dict, vlan_names):
    # Generate Interface Config
    sw_config = os9_getSwConfigDict(sw_facts)

    # Create os9_manifest, which is an os9 switch config as a dictionary for what the config manifests are
    os9_manifest = os9_convertNames(sw_config, intf_dict, vlan_dict, po_dict, vlan_names)
    os9_manifest = os9_generateConfig(os9_manifest)

    return os9_manifest

def os9_getFanoutConfigDict(intf_dict):
    # Get dict of fanout interfaces
    fanout_intf = { k: v for k, v in intf_dict.items() if "fanout" in v }
    out = {}

    # Generate correct stack-unit config
    for intf,fields in fanout_intf.items():
        port_num = intf.split("/")[1]
        fanout_cfg = fields["fanout"]
        fanout_speed = fields["fanout_speed"]

        conf_str = f"stack-unit 1 port {port_num} portmode {fanout_cfg} speed {fanout_speed}"

        out[conf_str] = {}

    return out

def os9_getConfig(sw_facts, intf_dict, vlan_dict, po_dict, vlan_names):
    os9_config = os9_getConfigDict(sw_facts, intf_dict, vlan_dict, po_dict, vlan_names)
    ansible_cfg = os9_manifestToAnsible(os9_config)

    return ansible_cfg

def os9_getFanoutConfig(sw_facts, intf_dict):
    os9_config = os9_getFanoutConfigDict(intf_dict)
    ansible_cfg = os9_manifestToAnsible(os9_config)

    return ansible_cfg

def os9_getConfigDiff(sw_facts, intf_dict, vlan_dict, po_dict, vlan_names, type = "on_switch"):
    def dict_diff(dict1, dict2):
        diff = {}
        for key, value in dict2.items():
            if key not in dict1:
                diff[key] = value
            elif isinstance(value, dict) and isinstance(dict1[key], dict):
                nested_diff = dict_diff(dict1[key], value)
                if nested_diff:
                    diff[key] = nested_diff

        return diff

    os9_manifest = os9_getConfigDict(sw_facts, intf_dict, vlan_dict, po_dict, vlan_names)
    os9_fanout = os9_getFanoutConfigDict(intf_dict)

    os9_manifest.update(os9_fanout)

    sw_config = os9_getSwConfigDict(sw_facts)

    if type == "on_switch":
        diff = dict_diff(os9_manifest, sw_config)
    elif type == "on_manifest":
        diff = dict_diff(sw_config, os9_manifest)

    return diff

# This class is required for ansible to find the filter plugins
class FilterModule(object):
    def filters(self):
        return {
            "os9_getConfig": os9_getConfig,
            "os9_getFanoutConfig": os9_getFanoutConfig,
            "os9_getConfigDiff": os9_getConfigDiff
        }
