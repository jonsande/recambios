from unittest.mock import Mock

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import RequestFactory, TestCase

from apps.catalog.models import Brand, Category, Condition, Product
from apps.suppliers.models import Supplier, SupplierUserAssignment
from apps.users.roles import ROLE_RESTRICTED_SUPPLIER
from apps.vehicles.admin import ProductVehicleFitmentAdmin
from apps.vehicles.models import ProductVehicleFitment, Vehicle


class ProductVehicleFitmentAdminBulkActionsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.site = AdminSite()
        cls.supplier = Supplier.objects.create(
            name="Supplier A",
            slug="supplier-a",
            code="SUP-A",
            is_active=True,
        )
        cls.parts_brand = Brand.objects.create(
            name="Valeo",
            slug="valeo",
            brand_type=Brand.BrandType.PARTS,
            is_active=True,
        )
        cls.vehicle_brand = Brand.objects.create(
            name="Audi",
            slug="audi",
            brand_type=Brand.BrandType.VEHICLE,
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
        cls.product = Product.objects.create(
            supplier=cls.supplier,
            sku="SKU-001",
            title="Alternator",
            category=cls.category,
            condition=cls.condition,
            brand=cls.parts_brand,
            publication_status=Product.PublicationStatus.DRAFT,
        )
        cls.vehicle_1 = Vehicle.objects.create(
            brand=cls.vehicle_brand,
            model="A3",
            vehicle_type=Vehicle.VehicleType.CAR,
            is_active=True,
        )
        cls.vehicle_2 = Vehicle.objects.create(
            brand=cls.vehicle_brand,
            model="A4",
            vehicle_type=Vehicle.VehicleType.CAR,
            is_active=True,
        )
        cls.fitment_1 = ProductVehicleFitment.objects.create(
            product=cls.product,
            vehicle=cls.vehicle_1,
            source=ProductVehicleFitment.FitmentSource.IMPORT,
            is_verified=False,
        )
        cls.fitment_2 = ProductVehicleFitment.objects.create(
            product=cls.product,
            vehicle=cls.vehicle_2,
            source=ProductVehicleFitment.FitmentSource.SUPPLIER,
            is_verified=True,
        )

        User = get_user_model()
        cls.staff_user = User.objects.create_user(
            username="staff-user",
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

        change_permission = Permission.objects.get(codename="change_productvehiclefitment")
        cls.staff_user.user_permissions.add(change_permission)
        cls.restricted_supplier_user.user_permissions.add(change_permission)

    def setUp(self):
        self.factory = RequestFactory()
        self.admin = ProductVehicleFitmentAdmin(ProductVehicleFitment, self.site)
        self.admin.message_user = Mock()

    def _request_for(self, user):
        request = self.factory.post("/admin/vehicles/productvehiclefitment/")
        request.user = user
        return request

    def test_bulk_action_can_mark_selected_fitments_as_verified(self):
        request = self._request_for(self.staff_user)
        queryset = ProductVehicleFitment.objects.filter(
            pk__in=[self.fitment_1.pk, self.fitment_2.pk]
        )

        self.admin.mark_selected_as_verified(request, queryset)

        self.fitment_1.refresh_from_db()
        self.fitment_2.refresh_from_db()
        self.assertTrue(self.fitment_1.is_verified)
        self.assertTrue(self.fitment_2.is_verified)

    def test_bulk_action_can_change_source_to_manual(self):
        request = self._request_for(self.staff_user)
        queryset = ProductVehicleFitment.objects.filter(
            pk__in=[self.fitment_1.pk, self.fitment_2.pk]
        )

        self.admin.set_source_manual(request, queryset)

        self.fitment_1.refresh_from_db()
        self.fitment_2.refresh_from_db()
        self.assertEqual(self.fitment_1.source, ProductVehicleFitment.FitmentSource.MANUAL)
        self.assertEqual(self.fitment_2.source, ProductVehicleFitment.FitmentSource.MANUAL)

    def test_bulk_actions_are_hidden_for_restricted_supplier_users(self):
        request = self._request_for(self.restricted_supplier_user)

        actions = self.admin.get_actions(request)

        self.assertNotIn("mark_selected_as_verified", actions)
        self.assertNotIn("mark_selected_as_unverified", actions)
        self.assertNotIn("set_source_supplier", actions)
        self.assertNotIn("set_source_import", actions)
        self.assertNotIn("set_source_manual", actions)

    def test_restricted_supplier_user_cannot_apply_bulk_source_update(self):
        request = self._request_for(self.restricted_supplier_user)
        queryset = ProductVehicleFitment.objects.filter(pk=self.fitment_1.pk)

        self.admin.set_source_manual(request, queryset)

        self.fitment_1.refresh_from_db()
        self.assertEqual(self.fitment_1.source, ProductVehicleFitment.FitmentSource.IMPORT)
