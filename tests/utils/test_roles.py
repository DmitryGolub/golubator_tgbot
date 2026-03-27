import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from tests.conftest import make_role, make_user
from src.utils.roles import is_admin


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
