import csv
import re
from dataclasses import dataclass
from datetime import datetime

import pandas as pd

INPUT_LOGS_PATH = "./kpf_logs.csv"
FILTERED_LOGS_PATH = "./filtered_logs.csv"
ROLES_PATH = "./roles.txt"
CUTOFF_DATETIME = "2023-01-01T00:00:00.0000000-04:00"
ROLE_SQL_FILE = "../sql/roles.sql"
CONTENT_SQL_FILE = "../sql/content.sql"


@dataclass
class RoleInfo:
    role_id: str
    member_name: str
    group_name: str
    string_tag: str


@dataclass
class ContentLink:
    role_id: str
    author_id: str
    author: str
    uploaded_date: datetime
    url: str
    initial_reaction_count: int = 0
    is_broken: bool = False


def get_parsed_roles(roles_path: str = ROLES_PATH) -> list[RoleInfo]:
    """Reads in text file with raw roles and returns the parsed dataclasses."""

    with open(roles_path, "r") as f:
        role_lines = f.readlines()

    # Pattern 1 in the form Dahyun [TWICE] 779824927611682836
    pattern1 = r"^(?P<name>.+?) \[(?P<group>.+?)\] (?P<role_id>\d+)$"
    # Pattern 2 in the form Cignature 779866230524739584; not technically always correct e.g. IU
    pattern2 = r"^(?P<group>.+?) (?P<role_id>\d+)$"

    role_infos = []
    for line in role_lines:
        string_tag = line.strip(" 0123456789\n")
        if match := re.match(pattern1, line):
            role_infos.append(
                RoleInfo(
                    member_name=match.group("name"),
                    group_name=match.group("group"),
                    role_id=match.group("role_id"),
                    string_tag=string_tag,
                )
            )
        elif match := re.match(pattern2, line):
            role_infos.append(
                RoleInfo(
                    member_name="",
                    group_name=match.group("group"),
                    role_id=match.group("role_id"),
                    string_tag=string_tag,
                )
            )
        else:
            raise ValueError(f"Can't parse role '{line}'")

    return role_infos


def filter_raw_logs(
    input_path: str = INPUT_LOGS_PATH, cutoff_datetime=CUTOFF_DATETIME, output_path: str = FILTERED_LOGS_PATH
) -> None:
    """Read in the raw logs and write out recent entries to a new file."""
    with open(input_path, mode="r", newline="", encoding="utf-8") as infile, open(
        output_path, mode="w", newline="", encoding="utf-8"
    ) as outfile:
        reader = csv.reader(infile)
        writer = csv.writer(outfile)

        # Write the header
        headers = next(reader)
        writer.writerow(headers)
        n_rows = 0

        for row in reader:
            if row[2] >= cutoff_datetime:
                writer.writerow(row)
                n_rows += 1
    print(f"Completed filtering, wrote {n_rows} records.")


def extract_allowed_urls_and_roles(content: str, role_tags: list[str]) -> tuple[list[str], list[str]]:
    """
    Extract URLs from the content that match the domains specified in the domain_allowlist
    and return a list of those URLs along with the list of matching roles found in the content.

    Args:
    content: The content to be checked.
    role_tags: A list of role tags to look for in the content.

    Returns:
    A tuple containing a list of URLs that match the allowed domains and a list of matching roles.
    """

    # Find all role IDs present in the content
    matching_roles = [role_tag for role_tag in role_tags if role_tag in content]

    # If no role IDs are found, return empty lists
    if not matching_roles:
        return [], []

    # Regular expression to find URLs in the content; very strict for now to exclude imgur albums
    urls = re.findall(r"https?://(?:i\.)?imgur\.com/[a-zA-Z0-9]{5,10}(?:\.mp4)?", content)

    return urls, matching_roles


def count_reactions(reaction_string: str) -> int:
    if not reaction_string:
        return 0

    # Find all matches in the string
    matches = re.findall(r"\((\d+)\)", reaction_string)

    # Convert matches to integers and sum them up
    total_reactions = sum(int(match) for match in matches)

    return total_reactions


def main() -> None:
    # Get roles and list of role ids
    roles = get_parsed_roles()
    role_tag_to_id = {role.string_tag: role.role_id for role in roles}

    # Do basic filtering of raw logs based on date
    filter_raw_logs()

    # Extract the content links from the filtered logs
    content_links: list[ContentLink] = []
    df = pd.read_csv(FILTERED_LOGS_PATH).astype(str)
    for _, row in df.iterrows():
        matched_urls, matched_role_tags = extract_allowed_urls_and_roles(row["Content"], list(role_tag_to_id.keys()))
        if not matched_urls or not matched_role_tags:
            continue
        react_count = count_reactions(row["Reactions"])
        for role_tag in matched_role_tags:
            for url in matched_urls:
                content_links.append(
                    ContentLink(
                        role_id=role_tag_to_id[role_tag],
                        author_id=row["AuthorID"],
                        author=row["Author"],
                        uploaded_date=datetime.fromisoformat(row["Date"]),
                        url=url,
                        initial_reaction_count=react_count,
                        is_broken=False,
                    )
                )

    # Write the role and content link tables out as SQL INSERT tuples
    with open(ROLE_SQL_FILE, "w") as f:
        f.write('INSERT INTO "role_info" ("role_id", "role_tag", "member_name", "group_name") VALUES\n')
        for i, role in enumerate(roles):
            text = f"\t('{role.role_id}', '{role.role_id}', '{role.member_name}', '{role.group_name}')"
            text += ";" if i == len(roles) - 1 else ","
            f.write(text + "\n")

    with open(CONTENT_SQL_FILE, "w") as f:
        f.write(
            'INSERT INTO "role_info" ("role_id", "author_id", "author", "uploaded_date", "url", "initial_reaction_count", "is_broken") VALUES\n'
        )
        for i, link in enumerate(content_links):
            text = (
                f"\t('{link.role_id}', '{link.author_id}', '{link.author}', '{link.uploaded_date.strftime('%Y-%m-%d %H:%M:%S')}'"
                f", '{link.url}', '{link.initial_reaction_count}', '{str(link.is_broken).lower()}'"
                ")"
            )
            text += ";" if i == len(roles) - 1 else ","
            f.write(text + "\n")


if __name__ == "__main__":
    main()
