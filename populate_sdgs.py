"""
Script to populate SDG (Sustainable Development Goals) data.
Run this after migrations: python manage.py shell < populate_sdgs.py
"""

from api.models import SDG

# 17 UN Sustainable Development Goals
SDGS = [
    {
        "code": "SDG1",
        "number": 1,
        "name": "No Poverty",
        "description": "End poverty in all its forms everywhere",
    },
    {
        "code": "SDG2",
        "number": 2,
        "name": "Zero Hunger",
        "description": "End hunger, achieve food security and improved nutrition and promote sustainable agriculture",
    },
    {
        "code": "SDG3",
        "number": 3,
        "name": "Good Health and Well-being",
        "description": "Ensure healthy lives and promote well-being for all at all ages",
    },
    {
        "code": "SDG4",
        "number": 4,
        "name": "Quality Education",
        "description": "Ensure inclusive and equitable quality education and promote lifelong learning opportunities for all",
    },
    {
        "code": "SDG5",
        "number": 5,
        "name": "Gender Equality",
        "description": "Achieve gender equality and empower all women and girls",
    },
    {
        "code": "SDG6",
        "number": 6,
        "name": "Clean Water and Sanitation",
        "description": "Ensure availability and sustainable management of water and sanitation for all",
    },
    {
        "code": "SDG7",
        "number": 7,
        "name": "Affordable and Clean Energy",
        "description": "Ensure access to affordable, reliable, sustainable and modern energy for all",
    },
    {
        "code": "SDG8",
        "number": 8,
        "name": "Decent Work and Economic Growth",
        "description": "Promote sustained, inclusive and sustainable economic growth, full and productive employment and decent work for all",
    },
    {
        "code": "SDG9",
        "number": 9,
        "name": "Industry, Innovation and Infrastructure",
        "description": "Build resilient infrastructure, promote inclusive and sustainable industrialization and foster innovation",
    },
    {
        "code": "SDG10",
        "number": 10,
        "name": "Reduced Inequality",
        "description": "Reduce inequality within and among countries",
    },
    {
        "code": "SDG11",
        "number": 11,
        "name": "Sustainable Cities and Communities",
        "description": "Make cities and human settlements inclusive, safe, resilient and sustainable",
    },
    {
        "code": "SDG12",
        "number": 12,
        "name": "Responsible Consumption and Production",
        "description": "Ensure sustainable consumption and production patterns",
    },
    {
        "code": "SDG13",
        "number": 13,
        "name": "Climate Action",
        "description": "Take urgent action to combat climate change and its impacts",
    },
    {
        "code": "SDG14",
        "number": 14,
        "name": "Life Below Water",
        "description": "Conserve and sustainably use the oceans, seas and marine resources for sustainable development",
    },
    {
        "code": "SDG15",
        "number": 15,
        "name": "Life on Land",
        "description": "Protect, restore and promote sustainable use of terrestrial ecosystems, sustainably manage forests, combat desertification, and halt and reverse land degradation and halt biodiversity loss",
    },
    {
        "code": "SDG16",
        "number": 16,
        "name": "Peace, Justice and Strong Institutions",
        "description": "Promote peaceful and inclusive societies for sustainable development, provide access to justice for all and build effective, accountable and inclusive institutions at all levels",
    },
    {
        "code": "SDG17",
        "number": 17,
        "name": "Partnerships for the Goals",
        "description": "Strengthen the means of implementation and revitalize the global partnership for sustainable development",
    },
]


def populate_sdgs() -> None:
    """Populate SDG data in the database."""
    created_count = 0
    updated_count = 0

    for sdg_data in SDGS:
        sdg, created = SDG.objects.get_or_create(
            code=sdg_data["code"],
            defaults={
                "name": sdg_data["name"],
                "number": sdg_data["number"],
                "description": sdg_data["description"],
            },
        )

        if created:
            created_count += 1
            print(f"Created: {sdg.code} - {sdg.name}")
        else:
            # Update existing SDG if needed
            if (
                sdg.name != sdg_data["name"]
                or sdg.number != sdg_data["number"]
                or sdg.description != sdg_data["description"]
            ):
                sdg.name = sdg_data["name"]  # type: ignore[assignment]
                sdg.number = sdg_data["number"]  # type: ignore[assignment]
                sdg.description = sdg_data["description"]  # type: ignore[assignment]
                sdg.save()
                updated_count += 1
                print(f"Updated: {sdg.code} - {sdg.name}")
            else:
                print(f"Already exists: {sdg.code} - {sdg.name}")

    print(
        f"\nSummary: Created {created_count}, Updated {updated_count}, Total {len(SDGS)}"
    )


# Auto-execute when loaded in Django shell
populate_sdgs()
