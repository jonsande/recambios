from django.db.models import Count, Q, QuerySet

from .models import Category, Product

PUBLIC_PRODUCT_FILTER = Q(
    is_active=True,
    publication_status=Product.PublicationStatus.PUBLISHED,
    published_at__isnull=False,
    supplier__is_active=True,
    category__is_active=True,
    condition__is_active=True,
) & (Q(brand__isnull=True) | Q(brand__is_active=True))

PUBLIC_CATEGORY_PRODUCT_FILTER = Q(
    products__is_active=True,
    products__publication_status=Product.PublicationStatus.PUBLISHED,
    products__published_at__isnull=False,
    products__supplier__is_active=True,
    products__condition__is_active=True,
) & (Q(products__brand__isnull=True) | Q(products__brand__is_active=True))


def get_public_products_queryset() -> QuerySet[Product]:
    return (
        Product.objects.filter(PUBLIC_PRODUCT_FILTER)
        .select_related("brand", "category", "condition", "supplier")
        .order_by("-featured", "-published_at", "-updated_at")
    )


def get_public_categories_queryset(*, with_counts: bool = False) -> QuerySet[Category]:
    queryset = Category.objects.filter(is_active=True).select_related("parent")
    if with_counts:
        queryset = queryset.annotate(
            public_product_count=Count(
                "products",
                filter=PUBLIC_CATEGORY_PRODUCT_FILTER,
                distinct=True,
            )
        )
    return queryset.order_by("sort_order", "name")
