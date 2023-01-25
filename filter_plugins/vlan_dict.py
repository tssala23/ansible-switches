def get_vlan_dict(vlan_dict, group_names):
    return {
        vlan: vlan_dict[vlan]
        for vlan in vlan_dict
        if type(vlan_dict[vlan]["switches"]) == list and \
            any(group in group_names for group in vlan_dict[vlan]["switches"])
    }


class FilterModule(object):
    def filters(self):
        return {"get_vlan_dict": get_vlan_dict}
