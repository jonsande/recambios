from unittest.mock import Mock

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import RequestFactory, TestCase
from django.utils import timezone

from apps.catalog.admin import ProductAdmin
from apps.catalog.models import Category, Condition, Product
from apps.suppliers.models import Supplier, SupplierUserAssignment
from apps.users.roles import ROLE_RESTRICTED_SUPPLIER


class ProductAdminBulkPublicationStatusTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.site = AdminSite()
        cls.supplier = Supplier.objects.create(
            name="Supplier A",
            slug="supplier-a",
            code="SUP-A",
            is_active=True,
        )
        cls.category = Category.objects.create(
            name="Alternators",
            slug="alternators",
            is_active=True,
        )
        cls.condition = Condition.objects.create(
            code="new",
            name="New",
            slug="new",
            is_active=True,
        )
        cls.draft_product = Product.objects.create(
            supplier=cls.supplier,
            sku="SKU-DRAFT-001",
            title="Draft product",
            category=cls.category,
            condition=cls.condition,
            publication_status=Product.PublicationStatus.DRAFT,
        )
        cls.review_product = Product.objects.create(
            supplier=cls.supplier,
            sku="SKU-REVIEW-001",
            title="Review product",
            category=cls.category,
            condition=cls.condition,
            publication_status=Product.PublicationStatus.REVIEW,
        )

        User = get_user_model()
        cls.publisher_user = User.objects.create_user(
            username="publisher",
            password="test-pass",
            is_staff=True,
        )
        cls.non_publisher_user = User.objects.create_user(
            username="editor",
            password="test-pass",
            is_staff=True,
        )
        cls.restricted_supplier_user = User.objects.create_user(
            username="supplier-user",
            password="test-pass",
            is_staff=True,
        )

        restricted_group, _ = Group.objects.get_or_create(name=ROLE_RESTRICTED_SUPPLIER)
        cls.restricted_supplier_user.groups.add(restricted_group)
        SupplierUserAssignment.objects.create(
            supplier=cls.supplier,
            user=cls.restricted_supplier_user,
            is_active=True,
        )

        change_permission = Permission.objects.get(codename="change_product")
        publish_permission = Permission.objects.get(codename="can_publish_product")
        cls.publisher_user.user_permissions.add(change_permission, publish_permission)
        cls.non_publisher_user.user_permissions.add(change_permission)
        cls.restricted_supplier_user.user_permissions.add(change_permission)

    def setUp(self):
        self.factory = RequestFactory()
        self.admin = ProductAdmin(Product, self.site)
        self.admin.message_user = Mock()

    def _request_for(self, user):
        request = self.factory.post("/admin/catalog/product/")
        request.user = user
        return request

    def test_authorized_user_can_publish_selected_products_in_bulk(self):
        request = self._request_for(self.publisher_user)
        queryset = Product.objects.filter(pk__in=[self.draft_product.pk, self.review_product.pk])

        self.admin.mark_selected_as_published(request, queryset)

        self.draft_product.refresh_from_db()
        self.review_product.refresh_from_db()
        self.assertEqual(
            self.draft_product.publication_status,
            Product.PublicationStatus.PUBLISHED,
        )
        self.assertEqual(
            self.review_product.publication_status,
            Product.PublicationStatus.PUBLISHED,
        )
        self.assertIsNotNone(self.draft_product.published_at)
        self.assertIsNotNone(self.review_product.published_at)

    def test_user_without_publish_permission_cannot_publish_in_bulk(self):
        request = self._request_for(self.non_publisher_user)
        queryset = Product.objects.filter(pk=self.draft_product.pk)

        self.admin.mark_selected_as_published(request, queryset)

        self.draft_product.refresh_from_db()
        self.assertEqual(self.draft_product.publication_status, Product.PublicationStatus.DRAFT)
        self.assertIsNone(self.draft_product.published_at)

    def test_restricted_supplier_user_can_only_move_drafts_to_review(self):
        request = self._request_for(self.restricted_supplier_user)
        queryset = Product.objects.filter(pk__in=[self.draft_product.pk, self.review_product.pk])

        self.admin.mark_selected_as_in_review(request, queryset)

        self.draft_product.refresh_from_db()
        self.review_product.refresh_from_db()
        self.assertEqual(self.draft_product.publication_status, Product.PublicationStatus.REVIEW)
        self.assertEqual(self.review_product.publication_status, Product.PublicationStatus.REVIEW)
        self.assertIsNone(self.draft_product.published_at)
        self.assertIsNone(self.review_product.published_at)

    def test_publish_action_is_hidden_for_restricted_supplier_users(self):
        request = self._request_for(self.restricted_supplier_user)

        actions = self.admin.get_actions(request)

        self.assertNotIn("mark_selected_as_published", actions)

    def test_publish_action_is_hidden_for_users_without_publish_permission(self):
        request = self._request_for(self.non_publisher_user)

        actions = self.admin.get_actions(request)

        self.assertNotIn("mark_selected_as_published", actions)

    def test_moving_published_product_back_to_draft_clears_published_at(self):
        published_product = Product.objects.create(
            supplier=self.supplier,
            sku="SKU-PUBLISHED-001",
            title="Published product",
            category=self.category,
            condition=self.condition,
            publication_status=Product.PublicationStatus.PUBLISHED,
            published_at=timezone.now(),
        )
        request = self._request_for(self.publisher_user)
        queryset = Product.objects.filter(pk=published_product.pk)

        self.admin.mark_selected_as_draft(request, queryset)

        published_product.refresh_from_db()
        self.assertEqual(published_product.publication_status, Product.PublicationStatus.DRAFT)
        self.assertIsNone(published_product.published_at)
