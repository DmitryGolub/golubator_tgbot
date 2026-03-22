import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from tests.conftest import make_role, make_user
from src.utils.roles import is_admin, is_mentor, is_student


def test_is_mentor_true():
    role = make_role(is_mentor=True)
    user = make_user(role_rel=role)
    assert is_mentor(user) is True


def test_is_mentor_false_with_student_role():
    role = make_role(is_mentor=False, is_student=True)
    user = make_user(role_rel=role)
    assert is_mentor(user) is False


def test_is_mentor_false_no_role():
    user = make_user(role_rel=None)
    assert is_mentor(user) is False


def test_is_student_true():
    role = make_role(is_student=True)
    user = make_user(role_rel=role)
    assert is_student(user) is True


def test_is_student_false():
    role = make_role(is_student=False)
    user = make_user(role_rel=role)
    assert is_student(user) is False


def test_is_admin_true():
    role = make_role(name="admin")
    user = make_user(role_rel=role)
    assert is_admin(user) is True


def test_is_admin_false():
    role = make_role(name="mentor")
    user = make_user(role_rel=role)
    assert is_admin(user) is False


def test_is_admin_no_role():
    user = make_user(role_rel=None)
    assert is_admin(user) is False
