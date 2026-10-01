#!/usr/bin/env python3
"""Audit a Letterboxd export against evidence-backed TMDB mappings, offline.

This does not publish content, fetch metadata, or rewrite the original export.
Review links use exact title/year only when unique in watched.csv; the export's
review URI identifies a review, not the film. Repeated reviews remain separate.
"""

import argparse
import collections
import csv
import hashlib
import io
import json
from pathlib import Path
import zipfile


def read_table(archive, name):
    return list(csv.DictReader(io.StringIO(archive.read(name).decode("utf-8-sig"))))


def write_csv(path, fields, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def audit(watched, reviews, manifest):
    excluded = {m['letterboxd_uri'] for m in manifest.get('excluded', [])}
    by_uri = {}
    by_title_year = collections.defaultdict(list)
    for film in watched:
        uri = film["Letterboxd URI"]
        if uri in by_uri:
            raise ValueError(f"Duplicate watched film URI: {uri}")
        by_uri[uri] = film
        by_title_year[(film["Name"], film["Year"])].append(uri)

    matches = {}
    for match in manifest["matches"]:
        uri = match["letterboxd_uri"]
        if uri in excluded:
            raise ValueError(f"Excluded film has an active mapping: {uri}")
        if uri in matches:
            raise ValueError(f"Duplicate mapping: {uri}")
        film = by_uri[uri]
        if (film["Name"], film["Year"]) != (match["title"], match["year"]):
            raise ValueError(f"Mapping differs from export: {uri}")
        if match["tmdb_type"] not in {"movie", "tv"} or not isinstance(match["tmdb_id"], int) or match["tmdb_id"] <= 0:
            raise ValueError(f"Invalid TMDB identifier: {uri}")
        matches[uri] = match

    unresolved = {m["letterboxd_uri"]: m for m in manifest.get("unresolved", [])}
    if matches.keys() & unresolved.keys():
        raise ValueError("A film cannot be both confirmed and unresolved")

    film_rows = []
    for uri, film in by_uri.items():
        if uri in excluded:
            continue
        match = matches.get(uri, {})
        film_rows.append({
            "title": film["Name"], "year": film["Year"], "letterboxd_uri": uri,
            "status": match.get('status', 'confirmed_link') if match else unresolved.get(uri, {}).get('status', 'unresolved') if uri in unresolved else "not_checked",
            "tmdb_type": match.get("tmdb_type", ""), "tmdb_id": match.get("tmdb_id", ""),
            "tmdb_url": f'https://www.themoviedb.org/{match["tmdb_type"]}/{match["tmdb_id"]}' if match else "",
            "source_url": match.get("source_url", ""),
            "note": match.get("note", unresolved.get(uri, {}).get("note", "")),
        })

    review_rows = []
    for number, review in enumerate(reviews, start=2):
        candidates = by_title_year[(review["Name"], review["Year"])]
        uri = candidates[0] if len(candidates) == 1 else ""
        if uri in excluded:
            continue
        match = matches.get(uri, {})
        review_rows.append({
            "source_csv_row": number, "review_uri": review["Letterboxd URI"],
            "title": review["Name"], "year": review["Year"],
            "watched_date": review["Watched Date"], "export_date": review["Date"],
            "film_letterboxd_uri": uri,
            "film_join": "unique_title_year" if uri else "ambiguous" if candidates else "missing",
            "tmdb_type": match.get("tmdb_type", ""), "tmdb_id": match.get("tmdb_id", ""),
            "needs_subject_review": "yes" if match.get("note") else "",
        })
    return film_rows, review_rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("export", type=Path)
    parser.add_argument("--mappings", type=Path, default=Path("data/film-matching/confirmed.json"))
    parser.add_argument("--output", type=Path, default=Path("data/film-matching"))
    args = parser.parse_args()
    manifest = json.loads(args.mappings.read_text(encoding="utf-8"))
    with zipfile.ZipFile(args.export) as archive:
        watched = read_table(archive, "watched.csv")
        reviews = read_table(archive, "reviews.csv")
        diary = read_table(archive, 'diary.csv')
    films, review_links = audit(watched, reviews, manifest)
    _, diary_links = audit(watched, diary, manifest)
    for row in diary_links:
        original = diary[row['source_csv_row'] - 2]
        row['rating'] = original['Rating']
        row['rewatch'] = original['Rewatch']
        row['entry_uri'] = row.pop('review_uri')
    diary_links.sort(key=lambda r: (r['watched_date'], r['source_csv_row']), reverse=True)
    args.output.mkdir(parents=True, exist_ok=True)
    write_csv(args.output / "films.csv", ["title", "year", "letterboxd_uri", "status", "tmdb_type", "tmdb_id", "tmdb_url", "source_url", "note"], films)
    write_csv(args.output / "review-links.csv", ["source_csv_row", "review_uri", "title", "year", "watched_date", "export_date", "film_letterboxd_uri", "film_join", "tmdb_type", "tmdb_id", "needs_subject_review"], review_links)
    write_csv(args.output / 'diary.csv', ['source_csv_row', 'entry_uri', 'title', 'year', 'watched_date', 'export_date', 'rating', 'rewatch', 'film_letterboxd_uri', 'film_join', 'tmdb_type', 'tmdb_id', 'needs_subject_review'], diary_links)
    summary = {
        "export_file": args.export.name,
        "export_sha256": hashlib.sha256(args.export.read_bytes()).hexdigest(),
        "scope": manifest.get('method', ''),
        "excluded_entries": len(manifest.get('excluded', [])),
        "watched_entries": len(films),
        "film_status_counts": dict(collections.Counter(f["status"] for f in films)),
        "review_entries": len(review_links),
        "review_film_join_counts": dict(collections.Counter(r["film_join"] for r in review_links)),
        "reviews_with_tmdb_mapping": sum(bool(r["tmdb_id"]) for r in review_links),
        "reviews_needing_subject_review": sum(r["needs_subject_review"] == "yes" for r in review_links),
        "diary_entries": len(diary_links),
        "diary_entries_with_tmdb_mapping": sum(bool(r['tmdb_id']) for r in diary_links),
    }
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
