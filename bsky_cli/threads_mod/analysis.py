from __future__ import annotations

from .api import get_profile, get_thread
from .models import Branch, InterlocutorProfile, TrackedThread
from .scoring import score_branch, score_interlocutor, score_thread_dynamics, score_topic_relevance
from .topics import calculate_topic_drift, extract_topics
from .utils import uri_to_url

def analyze_thread(pds: str, jwt: str, our_did: str, root_uri: str) -> TrackedThread | None:
    """
    Fully analyze a thread, extracting all branches we're involved in.
    """
    thread = get_thread(pds, jwt, root_uri, depth=20)
    if not thread:
        return None
    
    root_post = thread.get("post", {})
    root_record = root_post.get("record", {})
    root_text = root_record.get("text", "")
    root_author = root_post.get("author", {})
    
    main_topics = extract_topics(root_text)
    branches: dict[str, Branch] = {}
    our_reply_uris: list[str] = []
    our_reply_texts: list[str] = []  # For consistency checking
    all_interlocutor_dids: set[str] = set()
    engaged_interlocutors: set[str] = set()  # People we've replied to
    latest_activity = root_record.get("createdAt", "")
    
    def walk_thread(node: dict, parent_is_ours: bool = False, branch_key: str | None = None, parent_author_did: str | None = None):
        """Recursively walk thread to find our replies and track branches."""
        nonlocal latest_activity
        
        post = node.get("post", {})
        record = post.get("record", {})
        author = post.get("author", {})
        uri = post.get("uri", "")
        created = record.get("createdAt", "")
        text = record.get("text", "")
        author_did = author.get("did", "")
        author_handle = author.get("handle", "")
        is_ours = author_did == our_did
        
        if created and created > latest_activity:
            latest_activity = created
        
        # If this is our reply, it starts or continues a branch
        if is_ours:
            our_reply_uris.append(uri)
            our_reply_texts.append(text)  # Track our text for consistency
            # Track who we're engaging with
            if parent_author_did and parent_author_did != our_did:
                engaged_interlocutors.add(parent_author_did)
            if uri not in branches:
                branches[uri] = Branch(
                    our_reply_uri=uri,
                    our_reply_url=uri_to_url(uri),
                    interlocutors=[],
                    interlocutor_dids=[],
                    last_activity_at=created,
                    message_count=1,
                    topic_drift=0.0,
                    branch_score=0.0
                )
            branch_key = uri
        elif branch_key and branch_key in branches:
            # This is a reply to one of our branches
            branch = branches[branch_key]
            if author_handle and author_handle not in branch.interlocutors:
                branch.interlocutors.append(author_handle)
            if author_did and author_did not in branch.interlocutor_dids:
                branch.interlocutor_dids.append(author_did)
                all_interlocutor_dids.add(author_did)
            branch.message_count += 1
            if created > branch.last_activity_at:
                branch.last_activity_at = created
            # Accumulate text for topic drift calculation
            if not hasattr(branch, '_accumulated_text'):
                branch._accumulated_text = ""
            branch._accumulated_text += " " + text
        
        # Recurse into replies
        for reply in node.get("replies", []):
            walk_thread(reply, parent_is_ours=is_ours, branch_key=branch_key, parent_author_did=author_did)
    
    walk_thread(thread)
    
    # Calculate topic drift for each branch
    for branch in branches.values():
        branch_text = getattr(branch, '_accumulated_text', "")
        branch.topic_drift = calculate_topic_drift(root_text, branch_text)
        # Clean up temp attribute
        if hasattr(branch, '_accumulated_text'):
            delattr(branch, '_accumulated_text')
    
    # Fetch interlocutor profiles for scoring
    profiles: dict[str, InterlocutorProfile] = {}
    for did in all_interlocutor_dids:
        profile = get_profile(pds, jwt, did)
        if profile:
            profiles[did] = profile
    
    # Score branches (pass engaged_interlocutors to relax drift for ongoing conversations)
    for branch in branches.values():
        branch.branch_score = score_branch(branch, main_topics, profiles, engaged_interlocutors)
    
    # Calculate overall thread score
    total_replies = root_post.get("replyCount", 0)
    
    # Get root author profile for scoring
    root_profile = get_profile(pds, jwt, root_author.get("did", ""))
    interlocutor_score = 0
    if root_profile:
        interlocutor_score, _ = score_interlocutor(root_profile)
    
    topic_score, _ = score_topic_relevance(root_text)
    dynamics_score, _ = score_thread_dynamics(total_replies, len(our_reply_uris), len(branches))
    
    overall_score = interlocutor_score + topic_score + dynamics_score
    
    return TrackedThread(
        root_uri=root_uri,
        root_url=uri_to_url(root_uri),
        root_author_handle=root_author.get("handle", "unknown"),
        root_author_did=root_author.get("did", ""),
        main_topics=main_topics,
        root_text=root_text[:500],
        overall_score=overall_score,
        branches=branches,
        total_our_replies=len(our_reply_uris),
        created_at=root_record.get("createdAt", ""),
        last_activity_at=latest_activity,
        engaged_interlocutors=list(engaged_interlocutors),
        our_reply_texts=our_reply_texts[-10:]  # Keep last 10 for consistency checking
    )
