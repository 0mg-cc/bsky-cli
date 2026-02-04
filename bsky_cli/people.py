"""View and manage interlocutor history."""
from __future__ import annotations

import argparse

from . import interlocutors


def run(args) -> int:
    """Entry point from CLI."""
    
    # Stats mode
    if args.stats:
        s = interlocutors.stats()
        print("📊 Interlocutor Statistics\n")
        print(f"Total users tracked: {s['total_users']}")
        print(f"Regulars (3+ interactions): {s['regulars']}")
        print(f"Total interactions: {s['total_interactions']}")
        print(f"Average per user: {s['avg_per_user']:.1f}")
        return 0
    
    # Single user lookup
    if args.handle:
        handle = args.handle.lstrip("@")
        inter = interlocutors.get_by_handle(handle)
        
        if not inter:
            print(f"❌ No history with @{handle}")
            return 0
        
        badge = "🔄 Regular" if inter.is_regular else "👤 Known"
        print(f"{badge}: @{inter.handle}")
        if inter.display_name:
            print(f"Display name: {inter.display_name}")
        print(f"DID: {inter.did}")
        print(f"First seen: {inter.first_seen}")
        print(f"Last interaction: {inter.last_interaction}")
        print(f"Total interactions: {inter.total_count}")
        
        if inter.tags:
            print(f"Tags: {', '.join(inter.tags)}")
        
        if inter.notes:
            print(f"Notes: {inter.notes}")
        
        print(f"\n📜 Recent interactions:")
        for i in inter.recent_interactions(5):
            print(f"  [{i.date}] {i.type}")
            if i.their_text:
                print(f"    They: \"{i.their_text[:80]}{'...' if len(i.their_text) > 80 else ''}\"")
            if i.our_text:
                print(f"    Us:   \"{i.our_text[:80]}{'...' if len(i.our_text) > 80 else ''}\"")
        
        return 0
    
    # List mode
    if args.regulars:
        people = interlocutors.list_regulars()
        title = "🔄 Regular Interlocutors"
    else:
        people = interlocutors.list_all(min_interactions=1)
        title = "👥 All Known Interlocutors"
    
    if not people:
        print("No interlocutors tracked yet.")
        return 0
    
    people = people[:args.limit]
    
    print(f"{title} ({len(people)} shown)\n")
    
    for p in people:
        badge = "🔄" if p.is_regular else "  "
        tags_str = f" [{', '.join(p.tags)}]" if p.tags else ""
        print(f"{badge} @{p.handle}: {p.total_count} interactions (last: {p.last_interaction}){tags_str}")
    
    return 0


def main():
    parser = argparse.ArgumentParser(description="View interlocutor history")
    parser.add_argument("handle", nargs="?", help="Handle to look up")
    parser.add_argument("--regulars", action="store_true", help="Show regulars only")
    parser.add_argument("--stats", action="store_true", help="Show statistics")
    parser.add_argument("--limit", type=int, default=20, help="Max users to show")
    args = parser.parse_args()
    return run(args)


if __name__ == "__main__":
    exit(main())
