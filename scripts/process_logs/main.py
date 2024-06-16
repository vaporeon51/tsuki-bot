import re
from dataclasses import dataclass

ROLES_PATH = "./roles.txt"


@dataclass
class RoleInfo:
    member_name: str
    group_name: str
    role_id: str


def get_parsed_roles(roles_path: str = ROLES_PATH) -> list[RoleInfo]:
    with open(roles_path, "r") as f:
        role_lines = f.readlines()

    # Pattern 1 in the form Dahyun [TWICE] 779824927611682836
    pattern1 = r"^(?P<name>.+?) \[(?P<group>.+?)\] (?P<role_id>\d+)$"
    # Pattern 2 in the form Cignature 779866230524739584; not technically always correct e.g. IU
    pattern2 = r"^(?P<group>.+?) (?P<role_id>\d+)$"

    role_infos = []
    for line in role_lines:
        if match := re.match(pattern1, line):
            role_infos.append(
                RoleInfo(
                    member_name=match.group("name"), group_name=match.group("group"), role_id=match.group("role_id")
                )
            )
        elif match := re.match(pattern2, line):
            role_infos.append(RoleInfo(member_name="", group_name=match.group("group"), role_id=match.group("role_id")))
        else:
            raise ValueError(f"Can't parse role '{line}'")

    return role_infos


def main() -> None:
    roles = get_parsed_roles()
    print("Roles:\n", roles)


if __name__ == "__main__":
    main()
