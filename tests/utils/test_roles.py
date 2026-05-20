import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from types import SimpleNamespace

from tests.conftest import make_role, make_user
from src.utils.roles import is_admin, is_mentor


def _perm(codename: str) -> SimpleNamespace:
    return SimpleNamespace(codename=codename)


class TestIsAdmin:
    def test_true(self):
        role = make_role(name="admin", permissions=[_perm("all_permissions")])
        user = make_user(role_rel=role)
        assert is_admin(user) is True

    def test_false_no_all_permissions(self):
        role = make_role(name="mentor", permissions=[_perm("mentor_role")])
        user = make_user(role_rel=role)
        assert is_admin(user) is False

    def test_no_role(self):
        user = make_user(role_rel=None)
        assert is_admin(user) is False


class TestIsMentor:
    def test_true_mentor(self):
        role = make_role(
            name="mentor", permissions=[_perm("view_students"), _perm("mentor_role")]
        )
        user = make_user(role_rel=role)
        assert is_mentor(user) is True

    def test_true_direction_lead(self):
        role = make_role(
            name="direction_lead",
            permissions=[_perm("view_students"), _perm("mentor_role")],
        )
        user = make_user(role_rel=role)
        assert is_mentor(user) is True

    def test_false_student(self):
        role = make_role(
            name="student", permissions=[_perm("view_own_info"), _perm("fill_survey")]
        )
        user = make_user(role_rel=role)
        assert is_mentor(user) is False

    def test_no_role(self):
        user = make_user(role_rel=None)
        assert is_mentor(user) is False

    def test_empty_permissions(self):
        role = make_role(name="mentor", permissions=[])
        user = make_user(role_rel=role)
        assert is_mentor(user) is False

    def test_true_admin_all_permissions(self):
        role = make_role(name="admin", permissions=[_perm("all_permissions")])
        user = make_user(role_rel=role)
        assert is_mentor(user) is True
