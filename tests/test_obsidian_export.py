"""Behavior tests for the Obsidian one-way todo export.

Covers the two units that carry the logic:
  - markdown rendering (pure): frontmatter machinery + clean body, user-content preservation
  - the vault exporter: one-file-per-todo create/update/delete, ownership safety,
    frontmatter wikilinks, and cleanup of the prior (templated-block) structure
"""

from datetime import timezone

import pytest

from todo_app.obsidian import config as obs_config
from todo_app.obsidian import markdown
from todo_app.obsidian.factory import get_todo_exporter
from todo_app.obsidian.interface import ExportResult
from todo_app.obsidian.vault_exporter import ObsidianVaultExporter


UTC = timezone.utc


def _todo(**overrides):
    base = {
        "id": "todo_20260528_030019_8edbffd1",
        "user_id": "Alice",
        "title": "Acme versioning",
        "details": None,
        "due_at": None,
        "completed": False,
        "completed_at": None,
        "source_type": "manual",
        "group": None,
        "created_at": "2026-05-28T03:00:19+00:00",
        "updated_at": "2026-05-28T03:00:19+00:00",
        "source_metadata": {},
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------------------
# slugify
# --------------------------------------------------------------------------

def test_slugify_lowercases_and_hyphenates():
    assert markdown.slugify("Acme Versioning!") == "acme-versioning"


def test_slugify_falls_back_when_empty():
    assert markdown.slugify("   ") == "untitled"


def test_slugify_truncates_to_max_len():
    assert len(markdown.slugify("word " * 50, max_len=20)) <= 20


# --------------------------------------------------------------------------
# wikilink_name — safe display name for frontmatter links
# --------------------------------------------------------------------------

def test_wikilink_name_preserves_spaces_and_case():
    assert markdown.wikilink_name("Project Phoenix") == "Project Phoenix"


def test_wikilink_name_strips_link_breaking_characters():
    assert "[" not in markdown.wikilink_name("Side [Projects]")
    assert "]" not in markdown.wikilink_name("Side [Projects]")


# --------------------------------------------------------------------------
# render_todo_document — frontmatter machinery + clean body
# --------------------------------------------------------------------------

def test_document_puts_kind_and_status_in_frontmatter():
    doc = markdown.render_todo_document(_todo(), tz=UTC)
    assert doc.startswith("---\n")
    assert "doc_kind: todo" in doc
    assert f"{obs_config.MANAGED_FLAG_KEY}: true" in doc
    assert "status: open" in doc


def test_document_body_is_a_clean_title_heading():
    doc = markdown.render_todo_document(_todo(title="Acme versioning"), tz=UTC)
    body = doc.split("\n---\n", 1)[1]
    assert body.lstrip().startswith("# Acme versioning")


def test_document_has_no_templated_task_block_or_dataview_lines():
    """The old boilerplate that poisoned clustering must be gone."""
    doc = markdown.render_todo_document(
        _todo(group="Northwind", due_at="2026-06-01T00:00:00+00:00"), tz=UTC
    )
    assert "%% homeassist" not in doc     # no managed block markers in the body
    assert "- [ ]" not in doc             # no Tasks-plugin checkbox line
    assert "Project::" not in doc         # no Dataview inline field
    assert "#todo" not in doc             # no tag namespace


def test_completed_todo_marks_status_done_with_completed_at():
    doc = markdown.render_todo_document(
        _todo(completed=True, completed_at="2026-05-29T10:00:00+00:00"), tz=UTC
    )
    assert "status: done" in doc
    assert "completed_at:" in doc


def test_due_date_is_a_local_frontmatter_field():
    doc = markdown.render_todo_document(
        _todo(due_at="2026-06-01T00:00:00+00:00"), tz=UTC
    )
    assert "due: 2026-06-01" in doc


def test_document_includes_details_as_body_prose():
    doc = markdown.render_todo_document(_todo(details="Check the changelog"), tz=UTC)
    body = doc.split("\n---\n", 1)[1]
    assert "Check the changelog" in body
    assert ">" not in body.split(obs_config.USER_CONTENT_MARKER)[0]  # not a blockquote


def test_document_preserves_user_content_after_marker():
    existing = markdown.render_todo_document(_todo(), tz=UTC) + "\n## My notes\nkeep me\n"
    doc = markdown.render_todo_document(_todo(title="new title"), existing_text=existing, tz=UTC)
    assert "## My notes" in doc
    assert "keep me" in doc
    assert "# new title" in doc          # managed body refreshed


def test_document_migrates_user_tail_from_legacy_block_marker():
    """Notes from the prior (templated %%-block) version keep their user tail."""
    legacy = (
        "---\nhomeassist_managed: true\nid: x\n---\n"
        f"%% homeassist:todo:start %%\n- [ ] old\n{obs_config.MANAGED_BLOCK_END}\n"
        "\n## Legacy notes\nkeep me\n"
    )
    doc = markdown.render_todo_document(_todo(), existing_text=legacy, tz=UTC)
    assert "## Legacy notes" in doc
    assert "keep me" in doc
    assert "- [ ] old" not in doc


# --------------------------------------------------------------------------
# ObsidianVaultExporter — file lifecycle and ownership safety
# --------------------------------------------------------------------------

def _exporter(tmp_path):
    return ObsidianVaultExporter(vault_path=tmp_path, todos_subdir="Todos", tz=UTC)


def test_export_routes_open_and_completed_into_separate_folders(tmp_path):
    todos = [
        _todo(id="todo_a", title="Alpha"),
        _todo(id="todo_b", title="Beta", completed=True,
              completed_at="2026-05-29T10:00:00+00:00"),
    ]
    result = _exporter(tmp_path).export_user_todos(user="Alice", todos=todos)

    assert isinstance(result, ExportResult)
    assert result.success is True
    assert result.files_written == 2
    assert len(list((tmp_path / "Todos" / "Open").glob("*.md"))) == 1
    assert len(list((tmp_path / "Todos" / "Completed").glob("*.md"))) == 1


def test_completing_a_todo_moves_its_note_to_completed_preserving_user_notes(tmp_path):
    exporter = _exporter(tmp_path)
    exporter.export_user_todos(user="Alice", todos=[_todo(id="todo_a", title="Alpha")])

    note = next((tmp_path / "Todos" / "Open").glob("*.md"))
    note.write_text(note.read_text() + "\n## My notes\nimportant\n", encoding="utf-8")

    # Same id, now completed.
    exporter.export_user_todos(
        user="Alice",
        todos=[_todo(id="todo_a", title="Alpha", completed=True,
                     completed_at="2026-05-29T10:00:00+00:00")],
    )

    # The note moved folders — no copy left behind, no duplicate created.
    assert len(list((tmp_path / "Todos" / "Open").glob("*.md"))) == 0
    moved = list((tmp_path / "Todos" / "Completed").glob("*.md"))
    assert len(moved) == 1
    text = moved[0].read_text()
    assert "## My notes" in text          # user content carried across the move
    assert "status: done" in text         # managed frontmatter refreshed


def test_export_deletes_managed_file_for_removed_todo(tmp_path):
    exporter = _exporter(tmp_path)
    exporter.export_user_todos(
        user="Alice",
        todos=[_todo(id="todo_a", title="Alpha"), _todo(id="todo_b", title="Beta")],
    )
    assert len(list((tmp_path / "Todos").rglob("*.md"))) == 2

    result = exporter.export_user_todos(user="Alice", todos=[_todo(id="todo_a", title="Alpha")])

    assert result.files_deleted == 1
    assert len(list((tmp_path / "Todos").rglob("*.md"))) == 1


def test_export_self_heals_duplicate_orphan_notes(tmp_path):
    """A stale copy of a note (same id in two files, e.g. from a failed move) is
    deleted on the next export, leaving exactly one."""
    exporter = _exporter(tmp_path)
    exporter.export_user_todos(user="Alice", todos=[_todo(id="todo_a", title="Alpha")])
    note = next((tmp_path / "Todos" / "Open").glob("*.md"))
    # Simulate a leftover duplicate copy in the wrong folder.
    completed = tmp_path / "Todos" / "Completed"
    completed.mkdir(parents=True, exist_ok=True)
    (completed / "alpha.md").write_text(note.read_text(), encoding="utf-8")
    assert len(list((tmp_path / "Todos").rglob("*.md"))) == 2

    result = exporter.export_user_todos(user="Alice", todos=[_todo(id="todo_a", title="Alpha")])
    assert len(list((tmp_path / "Todos").rglob("*.md"))) == 1
    assert result.files_deleted == 1


def test_export_migrates_flat_legacy_note_into_status_folder(tmp_path):
    """A note left at the Todos root (old layout) is moved into Open/ on next run."""
    todos_dir = tmp_path / "Todos"
    todos_dir.mkdir(parents=True)
    legacy = todos_dir / "alpha.md"
    legacy.write_text(
        "---\nhomeassist_managed: true\nid: todo_a\ntitle: Alpha\nstatus: open\n---\n"
        f"%% homeassist:todo:start %%\n- [ ] Alpha\n{obs_config.MANAGED_BLOCK_END}\n",
        encoding="utf-8",
    )

    _exporter(tmp_path).export_user_todos(user="Alice", todos=[_todo(id="todo_a", title="Alpha")])

    assert not legacy.exists()
    assert len(list((todos_dir / "Open").glob("*.md"))) == 1


def test_export_never_deletes_unmanaged_notes(tmp_path):
    todos_dir = tmp_path / "Todos"
    todos_dir.mkdir(parents=True)
    user_note = todos_dir / "My Own Note.md"
    user_note.write_text("# Hand-written\n\nNot managed by HomeAssist.\n", encoding="utf-8")

    exporter = _exporter(tmp_path)
    # Export with no todos at all — must not touch the user's note.
    exporter.export_user_todos(user="Alice", todos=[])

    assert user_note.exists()
    assert "Hand-written" in user_note.read_text()


# --------------------------------------------------------------------------
# links — frontmatter wikilinks (project, chains, enrichment)
# --------------------------------------------------------------------------

def test_grouped_todo_links_project_in_frontmatter_and_no_hub_note(tmp_path):
    _exporter(tmp_path).export_user_todos(
        user="Alice", todos=[_todo(id="todo_a", title="Alpha", group="Northwind")]
    )

    note = next((tmp_path / "Todos" / "Open").glob("*.md"))
    assert 'project: "[[Northwind]]"' in note.read_text()
    # No project hub note is generated anymore.
    assert not (tmp_path / "Todos" / "Projects").exists()


def test_chained_todos_link_to_each_other_in_frontmatter(tmp_path):
    todos = [
        _todo(id="todo_a", title="Step one",
              source_metadata={"advanced_to": "todo_b"}),
        _todo(id="todo_b", title="Step two",
              source_metadata={"chain_parent_id": "todo_a"}),
    ]
    _exporter(tmp_path).export_user_todos(user="Alice", todos=todos)

    notes = {p.stem: p.read_text() for p in (tmp_path / "Todos" / "Open").glob("*.md")}
    assert 'next: "[[step-two]]"' in notes["step-one"]
    assert 'previous: "[[step-one]]"' in notes["step-two"]


def test_chain_link_to_todo_outside_export_is_omitted(tmp_path):
    # Neighbour todo_z is not in this export — no dangling link should be written.
    _exporter(tmp_path).export_user_todos(
        user="Alice",
        todos=[_todo(id="todo_a", title="Lonely",
                     source_metadata={"advanced_to": "todo_z"})],
    )
    note = next((tmp_path / "Todos" / "Open").glob("*.md"))
    assert "next:" not in note.read_text()


def test_enrichment_renders_people_and_related_links_in_frontmatter(tmp_path):
    from todo_app.todo_graph.types import TodoEnrichment

    todos = [
        _todo(id="todo_a", title="Call Bill"),
        _todo(id="todo_b", title="Email Bill"),
    ]
    enrichment = {
        "todo_a": TodoEnrichment(entities=["Bill"], related_ids=["todo_b", "todo_ghost"]),
        "todo_b": TodoEnrichment(entities=["Bill"], related_ids=["todo_a"]),
    }
    _exporter(tmp_path).export_user_todos(
        user="Alice", todos=todos, enrichment=enrichment
    )

    a_text = (tmp_path / "Todos" / "Open" / "call-bill.md").read_text()
    assert 'people: ["[[Bill]]"]' in a_text
    assert '"[[email-bill]]"' in a_text            # resolved neighbour in the export
    assert "todo_ghost" not in a_text             # id outside the export is dropped
    # No person hub note is generated anymore.
    assert not (tmp_path / "Todos" / "People").exists()


# --------------------------------------------------------------------------
# migration — the prior structure's hub/person stubs get cleaned up
# --------------------------------------------------------------------------

def test_legacy_project_and_person_hub_stubs_are_deleted(tmp_path):
    todos_dir = tmp_path / "Todos"
    (todos_dir / "Projects").mkdir(parents=True)
    (todos_dir / "People").mkdir(parents=True)
    (todos_dir / "Projects" / "Northwind.md").write_text(
        "---\nhomeassist_managed: true\nhomeassist_hub: group\ntitle: Northwind\n---\n# Northwind\n",
        encoding="utf-8",
    )
    (todos_dir / "People" / "Bill.md").write_text(
        "---\nhomeassist_managed: true\nhomeassist_hub: person\ntitle: Bill\n---\n# Bill\n",
        encoding="utf-8",
    )

    result = _exporter(tmp_path).export_user_todos(
        user="Alice", todos=[_todo(id="todo_a", title="Alpha", group="Northwind")]
    )

    assert not (todos_dir / "Projects" / "Northwind.md").exists()
    assert not (todos_dir / "People" / "Bill.md").exists()
    assert result.files_deleted == 2


# --------------------------------------------------------------------------
# factory — config-driven wiring
# --------------------------------------------------------------------------

def test_factory_returns_none_when_disabled(tmp_path):
    assert get_todo_exporter(enabled=False, vault_path=str(tmp_path)) is None


def test_factory_returns_none_when_vault_path_missing():
    assert get_todo_exporter(enabled=True, vault_path="") is None


def test_factory_returns_exporter_when_enabled_and_path_set(tmp_path):
    exporter = get_todo_exporter(enabled=True, vault_path=str(tmp_path))
    assert isinstance(exporter, ObsidianVaultExporter)
