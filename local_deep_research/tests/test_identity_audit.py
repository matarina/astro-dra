from research_verify.identity_audit import AuthoritativeIdentity, IdentityMention, audit_identity_mentions


def test_identity_audit_distinguishes_mismatch_match_and_unknown_without_deletion():
    registry = {
        "8": AuthoritativeIdentity("8", {
            "journal": "Cells", "year": 2026, "publication_type": "journal-article",
        }, {"kind": "Crossref", "doi": "10.3390/cells15181645"}),
        "9": AuthoritativeIdentity("9", {"journal": "Diabetes Metab J", "year": 2026}, {"kind": "Europe PMC"}),
    }
    mentions = [
        IdentityMention("wrong-journal", "8", claims={"journal": "Pharmacological Research", "year": 2026}),
        IdentityMention("correct-journal", "8", claims={"journal": "Cells", "year": 2026}),
        IdentityMention("unknown-author", "9", claims={"journal": "Diabetes Metab J", "authors": ""}),
    ]
    rows = audit_identity_mentions(mentions, registry)
    assert [row["status"] for row in rows] == ["mismatch", "match", "match"]
    assert rows[0]["field_results"]["journal"]["status"] == "mismatch"
    assert rows[2]["field_results"]["authors"]["status"] == "unknown"
    assert rows[0]["provenance"]["kind"] == "Crossref"
