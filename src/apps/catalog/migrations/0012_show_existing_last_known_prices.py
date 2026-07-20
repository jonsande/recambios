from django.db import migrations


def show_existing_last_known_prices(apps, schema_editor):
    Product = apps.get_model("catalog", "Product")
    Product.objects.filter(last_known_price__isnull=False).update(
        price_visibility_mode="visible_info"
    )


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0011_product_last_known_price_updated_at_and_more"),
    ]

    operations = [
        migrations.RunPython(
            show_existing_last_known_prices,
            migrations.RunPython.noop,
        ),
    ]
