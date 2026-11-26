"""
public_view_service.py - Stage 12 Public Timetable Read-Only Querying, Views & SEO
Serves Section, Faculty, Room, Master, Day, and Week views.
Supports case-insensitive search, combined filtering, SEO tags, robots.txt, and sitemap.xml.
Never queries mutable workspace state; queries solely from immutable public snapshots.
"""

import json
import os
import re
from typing import Dict, List, Optional, Any
from publication_service import PublicationService
from publication_models import PublicationStatus, Visibility

class PublicViewService:
    def __init__(self, publication_service: PublicationService):
        self.pub_service = publication_service

    def get_timetable_view(
        self,
        slug: str,
        view_type: str = "master",
        section: Optional[str] = None,
        faculty: Optional[str] = None,
        room: Optional[str] = None,
        subject: Optional[str] = None,
        day: Optional[int] = None,
        event_type: Optional[str] = None,
        query: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Main query endpoint for public viewer.
        Supports views: 'master', 'section', 'faculty', 'room', 'day', 'week'.
        Applies case-insensitive search and combined filtering.
        """
        snapshot = self.pub_service.get_public_snapshot_by_slug(slug)
        if not snapshot:
            return {"success": False, "error": "NOT_FOUND", "message": "Timetable publication not found."}
        if "error" in snapshot:
            return {
                "success": False,
                "error": snapshot["error"],
                "status": snapshot.get("status"),
                "message": f"This timetable publication is currently {snapshot.get('status', 'UNAVAILABLE')}."
            }

        events = snapshot["events"]

        def norm(s: str) -> str:
            return re.sub(r'[^a-zA-Z0-9]', '', str(s)).lower()

        # View-specific base filtering
        if view_type == "section" and section:
            sec_lower = section.strip().lower()
            sec_norm = norm(section)
            events = [
                e for e in events
                if e["section_name"].lower() == sec_lower
                or sec_lower in e["section_name"].lower()
                or sec_norm in norm(e["section_name"])
                or any(sec_norm in norm(s) for s in e.get("shared_sections", []))
            ]
        elif view_type == "faculty" and faculty:
            fac_lower = faculty.strip().lower()
            fac_norm = norm(faculty)
            events = [
                e for e in events
                if e["faculty_name"].lower() == fac_lower
                or fac_lower in e["faculty_name"].lower()
                or fac_norm in norm(e["faculty_name"])
                or any(fac_norm in norm(f) for f in e.get("multi_faculty", []))
            ]
        elif view_type == "room" and room:
            rm_lower = room.strip().lower()
            rm_norm = norm(room)
            events = [
                e for e in events
                if e["room_name"].lower() == rm_lower
                or rm_lower in e["room_name"].lower()
                or rm_norm in norm(e["room_name"])
            ]
        elif view_type == "day" and day is not None:
            events = [e for e in events if e["day"] == int(day)]

        # Secondary filtering
        if section and view_type != "section":
            sec_lower = section.strip().lower()
            events = [
                e for e in events
                if sec_lower in e["section_name"].lower()
                or any(sec_lower in s.lower() for s in e.get("shared_sections", []))
            ]

        if faculty and view_type != "faculty":
            fac_lower = faculty.strip().lower()
            events = [
                e for e in events
                if fac_lower in e["faculty_name"].lower()
                or any(fac_lower in f.lower() for f in e.get("multi_faculty", []))
            ]

        if room and view_type != "room":
            rm_lower = room.strip().lower()
            events = [e for e in events if rm_lower in e["room_name"].lower()]

        if subject:
            sub_lower = subject.strip().lower()
            events = [e for e in events if sub_lower in e["subject_name"].lower()]

        if day is not None and view_type != "day":
            events = [e for e in events if e["day"] == int(day)]

        if event_type:
            et_lower = event_type.strip().lower()
            events = [e for e in events if e["event_type"].lower() == et_lower]

        # Case-insensitive whitespace-tolerant search query
        if query and query.strip():
            q_clean = query.strip().lower()
            q_tokens = q_clean.split()
            filtered = []
            for ev in events:
                raw_searchable = f"{ev['subject_name']} {ev['faculty_name']} {ev['section_name']} {ev['room_name']} {ev['building']} {ev['day_name']} {ev['event_type']} {' '.join(ev.get('shared_sections', []))} {' '.join(ev.get('multi_faculty', []))}".lower()
                norm_searchable = norm(raw_searchable)
                if all(t in raw_searchable or norm(t) in norm_searchable for t in q_tokens):
                    filtered.append(ev)
            events = filtered

        # Grid restructuring for week/day/section/faculty/room views
        grid = self._build_grid_matrix(events, snapshot["time_slots"], snapshot["days"])

        return {
            "success": True,
            "view_type": view_type,
            "public_slug": slug,
            "publication_title": snapshot["title"],
            "institution_name": snapshot["institution_name"],
            "academic_period": snapshot["academic_period"],
            "effective_from": snapshot["effective_from"],
            "effective_to": snapshot["effective_to"],
            "published_at": snapshot["published_at"],
            "status": snapshot.get("status", "PUBLISHED"),
            "total_matching_events": len(events),
            "events": events,
            "grid": grid,
            "filter_options": {
                "sections": snapshot["sections"],
                "faculties": snapshot["faculties"],
                "rooms": snapshot["rooms"],
                "subjects": snapshot["subjects"],
                "days": snapshot["days"]
            },
            "seo": self.generate_seo_metadata(snapshot, view_type, section or faculty or room)
        }

    def _build_grid_matrix(self, events: List[Dict[str, Any]], time_slots: List[Dict[str, Any]], days: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Organizes events into a 5-day x 7-slot matrix with coherent 2-hour lab spans.
        """
        matrix = {d["day"]: {s["slot_index"]: [] for s in time_slots} for d in days}
        for ev in events:
            d = ev["day"]
            # match start time to slot
            st = ev["start_time"]
            slot_idx = 0
            for s in time_slots:
                if s["start_time"] == st:
                    slot_idx = s["slot_index"]
                    break
            if d in matrix and slot_idx in matrix[d]:
                matrix[d][slot_idx].append(ev)

        return {
            "days": days,
            "time_slots": time_slots,
            "slots_by_day": matrix
        }

    def generate_seo_metadata(self, snapshot: Dict[str, Any], view_type: str = "master", entity_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Generates production-grade SEO title, meta descriptions, canonical URLs, and Open Graph tags.
        """
        institution = snapshot.get("institution_name", "Woxsen University")
        period = snapshot.get("academic_period", "Spring 2026")
        title_base = snapshot.get("title", "Academic Timetable")
        slug = snapshot.get("public_slug", "")

        if view_type == "section" and entity_name:
            page_title = f"{entity_name} Timetable | {institution} ({period})"
            description = f"Official class timetable for {entity_name} at {institution} for {period}. View daily class schedules, labs, and faculty assignments."
            canonical = f"https://timetable.woxsen.edu.in/public/{slug}/section?name={entity_name}"
        elif view_type == "faculty" and entity_name:
            page_title = f"{entity_name} Faculty Schedule | {institution}"
            description = f"Faculty teaching timetable for {entity_name} at {institution} ({period}). View scheduled classes, room locations, and student sections."
            canonical = f"https://timetable.woxsen.edu.in/public/{slug}/faculty?name={entity_name}"
        elif view_type == "room" and entity_name:
            page_title = f"{entity_name} Room Schedule | {institution}"
            description = f"Occupancy and classroom schedule for {entity_name} at {institution} ({period})."
            canonical = f"https://timetable.woxsen.edu.in/public/{slug}/room?name={entity_name}"
        else:
            page_title = f"{title_base} ({period}) | {institution}"
            description = f"Official academic timetable for {institution}, {period}. View complete courses, sections, rooms, and weekly schedules."
            canonical = f"https://timetable.woxsen.edu.in/public/{slug}"

        is_public = snapshot.get("visibility") == Visibility.PUBLIC and snapshot.get("status") == PublicationStatus.PUBLISHED
        robots = "index, follow" if is_public else "noindex, nofollow"

        return {
            "title": page_title,
            "meta_description": description,
            "canonical_url": canonical,
            "robots": robots,
            "og_title": page_title,
            "og_description": description,
            "og_url": canonical,
            "og_type": "website",
            "twitter_card": "summary_large_image"
        }

    def generate_robots_txt(self) -> str:
        """
        Generates production-grade robots.txt.
        Disallows private, workspace, edit, review, and admin endpoints.
        Allows only /public/ for search engine indexation.
        """
        lines = [
            "User-agent: *",
            "Disallow: /admin/",
            "Disallow: /api/auth/",
            "Disallow: /api/projects/",
            "Disallow: /api/versioning/",
            "Disallow: /api/review/",
            "Disallow: /api/approval/",
            "Disallow: /api/feasibility/",
            "Disallow: /api/generation/",
            "Disallow: /api/simulation/",
            "Disallow: /editor/",
            "Disallow: /workspace/",
            "Allow: /public/",
            "Allow: /assets/",
            "",
            "Sitemap: https://timetable.woxsen.edu.in/sitemap.xml"
        ]
        return "\n".join(lines)

    def generate_sitemap_xml(self) -> str:
        """
        Generates sitemap.xml containing ONLY publicly published, indexable timetable URLs.
        Strictly excludes private, unlisted, draft, superseded, or unpublished timetables.
        """
        registry = self.pub_service._load_registry()
        public_urls = []

        for p in registry:
            if p.get("status") == PublicationStatus.PUBLISHED and p.get("visibility") == Visibility.PUBLIC:
                slug = p["public_slug"]
                lastmod = p.get("updated_at") or p.get("published_at")
                if lastmod and "T" in lastmod:
                    lastmod_date = lastmod.split("T")[0]
                else:
                    lastmod_date = "2026-01-01"
                public_urls.append(f"""  <url>
    <loc>https://timetable.woxsen.edu.in/public/{slug}</loc>
    <lastmod>{lastmod_date}</lastmod>
    <changefreq>weekly</changefreq>
    <priority>0.9</priority>
  </url>""")

        xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://timetable.woxsen.edu.in/</loc>
    <changefreq>daily</changefreq>
    <priority>1.0</priority>
  </url>
{chr(10).join(public_urls)}
</urlset>"""
        return xml_content

    @staticmethod
    def get_security_headers() -> Dict[str, str]:
        """
        Returns production-grade HTTP security headers for all responses.
        Protects against MIME sniffing, clickjacking, XSS, and unauthorized embeddings.
        """
        return {
            "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; frame-ancestors 'none';",
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains; preload"
        }
