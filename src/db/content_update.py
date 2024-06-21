from dataclasses import dataclass
from datetime import datetime

import psycopg

from . import CONN_DICT


@dataclass
class ContentLink:
    role_id: str
    author_id: str
    author: str
    uploaded_date: datetime
    url: str
    processed_date: datetime
    initial_reaction_count: int = 0
    num_upvotes = 0
    num_reports = 0

    def to_value_string(self) -> str:
        return (
            f"('{self.role_id}', '{self.author_id}', '{self.author}', "
            f"'{self.uploaded_date.strftime('%Y-%m-%d %H:%M:%S')}', "
            f"'{self.url}', "
            f"{self.initial_reaction_count}, "
            f"{self.num_upvotes}, "
            f"{self.num_reports}, "
            f"'{self.processed_date.strftime('%Y-%m-%d %H:%M:%S')}')"
        )


def get_latest_message_id() -> tuple[datetime, str]:
    with psycopg.connect(**CONN_DICT) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT last_message_id
                FROM update_log
                WHERE processed_date = (
                    SELECT MAX(processed_date) FROM update_log
                )
                """
            )
            result = cur.fetchone()
    assert result is not None and len(result) == 1, f"Unexpected latest update: {result}"
    return result[0]


def get_role_ids() -> list[str]:
    with psycopg.connect(**CONN_DICT) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT role_id FROM role_info")
            result = cur.fetchall()
    assert result is not None and len(result) > 0, f"Unexpected roles list: {result}"
    return [row[0] for row in result]


def upsert_content_links_and_update_logs(
    processed_date: datetime, last_message_id: str, new_links: list[ContentLink]
) -> None:
    with psycopg.connect(**CONN_DICT) as conn:
        with conn.cursor() as cur:
            try:
                # Upsert content links
                cur.execute(
                    f"""
                    INSERT INTO "content_links" ("role_id", "author_id", "author", "uploaded_date", "url", "initial_reaction_count", "num_upvotes", "num_reports", "processed_date") VALUES
                        {", ".join(link.to_value_string() for link in new_links)};
                    """,
                )

                # Update logs
                cur.execute(
                    """
                    INSERT INTO "update_log" ("processed_date", "last_message_id", "rows_inserted") VALUES
                        (%s, %s, %s);
                    """,
                    (processed_date.strftime("%Y-%m-%d %H:%M:%S"), last_message_id, len(new_links)),
                )

                # Commit the transaction
                conn.commit()
                print(f"Finished writing {len(new_links)} to database and updated logs.")

            except Exception as e:
                # Rollback the transaction on error
                conn.rollback()
                print(f"Upsert and update failed, rolled back. Error:{e}")
                raise e
