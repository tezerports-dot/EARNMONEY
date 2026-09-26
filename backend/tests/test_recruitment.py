"""Recruitment postings: the app lists only open ones, and only what the admin
actually posted — nothing is shown by default (CLAUDE.md product-integrity)."""

from __future__ import annotations

from sqlalchemy import text

from app import db
from tests.helpers import auth, signup
from tests.test_admin_web import admin_login


async def add_post(title: str, *, is_open: bool = True, sort: int = 0) -> None:
    async with db.sessionmaker()() as s, s.begin():
        await s.execute(
            text("INSERT INTO recruitment_posts (title, description, is_open, sort_order) VALUES (:t, :d, :o, :s)"),
            {"t": title, "d": f"About {title}", "o": is_open, "s": sort},
        )


async def test_recruitment_tab_is_empty_by_default(client):
    body = await signup(client)
    r = await client.get("/v1/recruitment", headers=auth(body["tokens"]))
    assert r.status_code == 200 and r.json() == {"posts": []}


async def test_only_open_posts_are_listed(client):
    await add_post("Backend Engineer", is_open=True, sort=1)
    await add_post("Old Role", is_open=False, sort=2)
    body = await signup(client)
    posts = (await client.get("/v1/recruitment", headers=auth(body["tokens"]))).json()["posts"]
    assert [p["title"] for p in posts] == ["Backend Engineer"]
    assert posts[0]["description"] == "About Backend Engineer"


async def test_admin_can_post_and_close_a_job(client):
    csrf = await admin_login(client)
    form = {
        "csrf": csrf,
        "title": "Community Manager",
        "location": "Bengaluru",
        "employment_type": "Full-time",
        "description": "Run the launch community.",
        "apply_email": "jobs@futurefashion.example",
        "sort_order": "0",
        "is_open": "on",
    }
    assert (await client.post("/admin/recruitment/save", data=form)).status_code == 303
    body = await signup(client)
    posts = (await client.get("/v1/recruitment", headers=auth(body["tokens"]))).json()["posts"]
    assert len(posts) == 1 and posts[0]["title"] == "Community Manager" and posts[0]["location"] == "Bengaluru"

    # Re-saving without "is_open" closes it, so it leaves the app.
    async with db.sessionmaker()() as s, s.begin():
        post_id = (await s.execute(text("SELECT id FROM recruitment_posts"))).scalar_one()
    closed = {**form, "id": str(post_id), "is_open": ""}
    assert (await client.post("/admin/recruitment/save", data=closed)).status_code == 303
    assert (await client.get("/v1/recruitment", headers=auth(body["tokens"]))).json() == {"posts": []}
