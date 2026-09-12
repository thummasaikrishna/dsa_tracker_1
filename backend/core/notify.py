"""Helpers to create notifications without duplicates."""

from django.db.models import Count, Q
from django.utils import timezone

from .models import Assignment, Notification, Profile, Question


def _active_student_ids():
    return list(
        Profile.objects.filter(role="user", is_removed=False).values_list("user_id", flat=True)
    )


def notify_students_new_question(question: Question):
    student_ids = _active_student_ids()
    if not student_ids:
        return
    existing = set(
        Notification.objects.filter(
            event=Notification.EVENT_NEW_QUESTION, question=question
        ).values_list("user_id", flat=True)
    )
    rows = [
        Notification(
            user_id=uid,
            event=Notification.EVENT_NEW_QUESTION,
            title="New Question Added",
            message=f"A new DSA problem has been added: {question.title}",
            question=question,
        )
        for uid in student_ids
        if uid not in existing
    ]
    if rows:
        Notification.objects.bulk_create(rows, ignore_conflicts=True)


def notify_students_question_updated(question: Question):
    """One update notification per student per question; refresh it on later edits."""
    student_ids = _active_student_ids()
    if not student_ids:
        return
    now = timezone.now()
    title = "Question Updated"
    message = f"The problem '{question.title}' has been updated."
    existing = {
        n.user_id: n
        for n in Notification.objects.filter(
            event=Notification.EVENT_QUESTION_UPDATED, question=question, user_id__in=student_ids
        )
    }
    to_create = []
    to_update = []
    for uid in student_ids:
        row = existing.get(uid)
        if row:
            row.title = title
            row.message = message
            if not row.is_dismissed:
                row.is_read = False
                row.created_at = now
            to_update.append(row)
        else:
            to_create.append(
                Notification(
                    user_id=uid,
                    event=Notification.EVENT_QUESTION_UPDATED,
                    title=title,
                    message=message,
                    question=question,
                )
            )
    if to_create:
        Notification.objects.bulk_create(to_create, ignore_conflicts=True)
    if to_update:
        Notification.objects.bulk_update(to_update, ["title", "message", "is_read", "created_at"])


def notify_student_proof_validated(assignment):
    points = assignment.points_awarded
    Notification.objects.get_or_create(
        user_id=assignment.user_id,
        event=Notification.EVENT_PROOF_VALIDATED,
        assignment=assignment,
        defaults={
            "title": "YOUR SOLUTION HAS BEEN VALIDATED",
            "message": (
                f"Question: {assignment.question.title}\n"
                f"Points Earned: +{points} ⭐"
            ),
            "question_id": assignment.question_id,
        },
    )


def notify_student_proof_rejected(assignment):
    Notification.objects.get_or_create(
        user_id=assignment.user_id,
        event=Notification.EVENT_PROOF_REJECTED,
        assignment=assignment,
        defaults={
            "title": "Your solution was not validated",
            "message": (
                f'Your LinkedIn proof for "{assignment.question.title}" was rejected. '
                "Points Earned: 0"
            ),
            "question_id": assignment.question_id,
        },
    )


def notify_admin_proof_submitted(assignment):
    """Create a dismissible admin notification while leaving proof review unchanged."""
    admin = Profile.objects.filter(role="admin", is_removed=False).select_related("user").first()
    if not admin:
        return
    student = assignment.user.get_full_name() or assignment.user.username
    Notification.objects.get_or_create(
        user=admin.user,
        event=Notification.EVENT_PROOF_SUBMITTED,
        assignment=assignment,
        defaults={
            "title": "NEW PROOF SUBMISSION",
            "message": f"{student} submitted a LinkedIn proof for {assignment.question.title}.",
            "question_id": assignment.question_id,
            "about_user_id": assignment.user_id,
        },
    )


def notify_admin_code_submitted(submission: "CodeSubmission"):
    admins = list(Profile.objects.filter(role="admin", is_removed=False).select_related("user"))
    if not admins:
        return
    student = submission.user.get_full_name() or submission.user.username
    language = dict(submission.LANGUAGE_CHOICES).get(submission.language, submission.language)
    status = dict(submission.STATUS_CHOICES).get(submission.status, submission.status)
    submitted = timezone.localtime(submission.submitted_at).strftime("%B %d, %Y, %I:%M %p")
    for admin in admins:
        Notification.objects.get_or_create(
            user=admin.user,
            event=Notification.EVENT_CODE_SUBMITTED,
            code_submission=submission,
            defaults={
                "title": "NEW CODE SUBMISSION",
                "message": (
                    f"Student Name: {student}\n"
                    f"Question: {submission.question.title}\n"
                    f"Language: {language}\n"
                    f"Submission Result: {status}\n"
                    f"Submitted At: {submitted}"
                ),
                "question_id": submission.question_id,
                "about_user_id": submission.user_id,
            },
        )


def notify_student_code_result(submission: "CodeSubmission"):
    title = (
        "SOLUTION ACCEPTED"
        if submission.status == submission.STATUS_ACCEPTED
        else "SOLUTION NOT ACCEPTED"
    )
    status = dict(submission.STATUS_CHOICES).get(submission.status, submission.status)
    if submission.status == submission.STATUS_ACCEPTED:
        message = (
            f"Question: {submission.question.title}\n"
            f"Tests Passed: {submission.tests_passed} / {submission.total_tests}\n"
            f"Points Earned: +{submission.points_awarded} ⭐"
        )
    else:
        message = (
            f"Question: {submission.question.title}\n"
            f"Status: {status}\n"
            f"Tests Passed: {submission.tests_passed} / {submission.total_tests}"
        )
    Notification.objects.get_or_create(
        user_id=submission.user_id,
        event=Notification.EVENT_CODE_RESULT,
        code_submission=submission,
        defaults={
            "title": title,
            "message": message,
            "question_id": submission.question_id,
        },
    )


def student_activity_snapshot(user_id):
    agg = Assignment.objects.filter(user_id=user_id).aggregate(
        assigned_count=Count("id"),
        proof_count=Count("id", filter=~Q(proof_status="none")),
    )
    assigned = agg["assigned_count"] or 0
    proofs = agg["proof_count"] or 0
    if assigned == 0:
        state = "no_activity"
    elif proofs == 0:
        state = "inactive"
    else:
        state = "active"
    return {
        "assigned_count": assigned,
        "proof_count": proofs,
        "activity_state": state,
        "is_inactive": assigned == 0 or proofs == 0,
    }


def sync_admin_inactivity_notifications():
    """
    One inactivity notification per admin+student. Recreated only if missing.
    When the student becomes active (has assignments AND at least one proof),
    unread inactivity alerts are marked read so they stop occupying the badge.
    """
    admin_profile = Profile.objects.filter(role="admin", is_removed=False).select_related("user").first()
    if not admin_profile:
        return
    admin_user = admin_profile.user
    students = Profile.objects.filter(role="user", is_removed=False).select_related("user")
    for profile in students:
        snap = student_activity_snapshot(profile.user_id)
        display = profile.user.get_full_name() or profile.user.username
        if snap["is_inactive"]:
            obj, created = Notification.objects.get_or_create(
                user=admin_user,
                event=Notification.EVENT_STUDENT_INACTIVE,
                about_user=profile.user,
                defaults={
                    "title": "Student Inactivity Alert",
                    "message": (
                        f"Student {display} has not performed any DSA activity. "
                        f"Assigned Questions: {snap['assigned_count']}. "
                        f"Proof Submissions: {snap['proof_count']}."
                    ),
                },
            )
            if not created:
                obj.title = "Student Inactivity Alert"
                obj.message = (
                    f"Student {display} has not performed any DSA activity. "
                    f"Assigned Questions: {snap['assigned_count']}. "
                    f"Proof Submissions: {snap['proof_count']}."
                )
                obj.save(update_fields=["title", "message"])
        else:
            Notification.objects.filter(
                user=admin_user,
                event=Notification.EVENT_STUDENT_INACTIVE,
                about_user=profile.user,
                is_read=False,
            ).update(is_read=True)
