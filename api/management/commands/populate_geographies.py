"""
Django management command to populate Asia Pacific geography data.
Covers: India, Indonesia, Thailand, Philippines at state/province level.

Usage:
    python manage.py populate_geographies
    python manage.py populate_geographies --clear  # Clear existing data first
"""

from typing import Any

from django.core.management.base import BaseCommand, CommandParser
from django.db import transaction

from api.models import Geography
from api.utils.enums import GeoTypes


class Command(BaseCommand):
    help = (
        "Populate Asia Pacific geography data (India, Indonesia, Thailand, Philippines)"
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear all existing geography data before populating",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        clear_existing = options.get("clear", False)

        if clear_existing:
            self.stdout.write(self.style.WARNING("Clearing existing geography data..."))
            Geography.objects.all().delete()
            self.stdout.write(self.style.SUCCESS("✓ Cleared existing data"))

        with transaction.atomic():
            self._populate_geographies()

        self.stdout.write(
            self.style.SUCCESS(
                f"\n✅ Successfully populated {Geography.objects.count()} geography entries"
            )
        )

    def _populate_geographies(self) -> None:
        """Populate geography data in an idempotent way."""

        # Create or get Asia Pacific region
        asia_pacific, created = Geography.objects.get_or_create(
            name="Asia Pacific", defaults={"code": "APAC", "type": GeoTypes.REGION}
        )
        if created:
            self.stdout.write(f"Created region: {asia_pacific.name}")
        else:
            self.stdout.write(f"Region already exists: {asia_pacific.name}")

        # India and its states
        self._populate_india(asia_pacific)

        # Indonesia and its provinces
        self._populate_indonesia(asia_pacific)

        # Thailand and its provinces
        self._populate_thailand(asia_pacific)

        # Philippines and its provinces
        self._populate_philippines(asia_pacific)

    def _populate_india(self, parent: Geography) -> None:
        """Populate India and its states/UTs."""
        india, created = Geography.objects.get_or_create(
            name="India",
            defaults={"code": "IN", "type": GeoTypes.COUNTRY, "parent_id": parent},
        )
        if created:
            self.stdout.write(f"Created country: {india.name}")
        else:
            self.stdout.write(f"Country already exists: {india.name}")

        indian_states = [
            ("Andhra Pradesh", "AP"),
            ("Arunachal Pradesh", "AR"),
            ("Assam", "AS"),
            ("Bihar", "BR"),
            ("Chhattisgarh", "CT"),
            ("Goa", "GA"),
            ("Gujarat", "GJ"),
            ("Haryana", "HR"),
            ("Himachal Pradesh", "HP"),
            ("Jharkhand", "JH"),
            ("Karnataka", "KA"),
            ("Kerala", "KL"),
            ("Madhya Pradesh", "MP"),
            ("Maharashtra", "MH"),
            ("Manipur", "MN"),
            ("Meghalaya", "ML"),
            ("Mizoram", "MZ"),
            ("Nagaland", "NL"),
            ("Odisha", "OR"),
            ("Punjab", "PB"),
            ("Rajasthan", "RJ"),
            ("Sikkim", "SK"),
            ("Tamil Nadu", "TN"),
            ("Telangana", "TG"),
            ("Tripura", "TR"),
            ("Uttar Pradesh", "UP"),
            ("Uttarakhand", "UT"),
            ("West Bengal", "WB"),
            ("Andaman and Nicobar Islands", "AN"),
            ("Chandigarh", "CH"),
            ("Dadra and Nagar Haveli and Daman and Diu", "DN"),
            ("Delhi", "DL"),
            ("Jammu and Kashmir", "JK"),
            ("Ladakh", "LA"),
            ("Lakshadweep", "LD"),
            ("Puducherry", "PY"),
        ]

        created_count = 0
        for state_name, state_code in indian_states:
            _, created = Geography.objects.get_or_create(
                name=state_name,
                defaults={
                    "code": state_code,
                    "type": GeoTypes.STATE,
                    "parent_id": india,
                },
            )
            if created:
                created_count += 1

        self.stdout.write(
            f"Indian states/UTs: {created_count} created, {len(indian_states) - created_count} already existed"
        )

    def _populate_indonesia(self, parent: Geography) -> None:
        """Populate Indonesia and its provinces."""
        indonesia, created = Geography.objects.get_or_create(
            name="Indonesia",
            defaults={"code": "ID", "type": GeoTypes.COUNTRY, "parent_id": parent},
        )
        if created:
            self.stdout.write(f"Created country: {indonesia.name}")
        else:
            self.stdout.write(f"Country already exists: {indonesia.name}")

        indonesian_provinces = [
            ("Aceh", "AC"),
            ("Bali", "BA"),
            ("Banten", "BT"),
            ("Bengkulu", "BE"),
            ("Central Java", "JT"),
            ("Central Kalimantan", "KT"),
            ("Central Sulawesi", "ST"),
            ("East Java", "JI"),
            ("East Kalimantan", "KI"),
            ("East Nusa Tenggara", "NT"),
            ("Gorontalo", "GO"),
            ("Jakarta", "JK"),
            ("Jambi", "JA"),
            ("Lampung", "LA"),
            ("Maluku", "MA"),
            ("North Kalimantan", "KU"),
            ("North Maluku", "MU"),
            ("North Sulawesi", "SA"),
            ("North Sumatra", "SU"),
            ("Papua", "PA"),
            ("Riau", "RI"),
            ("Riau Islands", "KR"),
            ("South Kalimantan", "KS"),
            ("South Sulawesi", "SN"),
            ("South Sumatra", "SS"),
            ("Southeast Sulawesi", "SG"),
            ("West Java", "JB"),
            ("West Kalimantan", "KB"),
            ("West Nusa Tenggara", "NB"),
            ("West Papua", "PB"),
            ("West Sulawesi", "SR"),
            ("West Sumatra", "SB"),
            ("Yogyakarta", "YO"),
        ]

        created_count = 0
        for province_name, province_code in indonesian_provinces:
            _, created = Geography.objects.get_or_create(
                name=province_name,
                defaults={
                    "code": province_code,
                    "type": GeoTypes.STATE,
                    "parent_id": indonesia,
                },
            )
            if created:
                created_count += 1

        self.stdout.write(
            f"Indonesian provinces: {created_count} created, {len(indonesian_provinces) - created_count} already existed"
        )

    def _populate_thailand(self, parent: Geography) -> None:
        """Populate Thailand and its provinces."""
        thailand, created = Geography.objects.get_or_create(
            name="Thailand",
            defaults={"code": "TH", "type": GeoTypes.COUNTRY, "parent_id": parent},
        )
        if created:
            self.stdout.write(f"Created country: {thailand.name}")
        else:
            self.stdout.write(f"Country already exists: {thailand.name}")

        thai_provinces = [
            ("Bangkok", "BKK"),
            ("Amnat Charoen", "37"),
            ("Ang Thong", "15"),
            ("Bueng Kan", "38"),
            ("Buriram", "31"),
            ("Chachoengsao", "24"),
            ("Chai Nat", "18"),
            ("Chaiyaphum", "36"),
            ("Chanthaburi", "22"),
            ("Chiang Mai", "50"),
            ("Chiang Rai", "57"),
            ("Chonburi", "20"),
            ("Chumphon", "86"),
            ("Kalasin", "46"),
            ("Kamphaeng Phet", "62"),
            ("Kanchanaburi", "71"),
            ("Khon Kaen", "40"),
            ("Krabi", "81"),
            ("Lampang", "52"),
            ("Lamphun", "51"),
            ("Loei", "42"),
            ("Lopburi", "16"),
            ("Mae Hong Son", "58"),
            ("Maha Sarakham", "44"),
            ("Mukdahan", "49"),
            ("Nakhon Nayok", "26"),
            ("Nakhon Pathom", "73"),
            ("Nakhon Phanom", "48"),
            ("Nakhon Ratchasima", "30"),
            ("Nakhon Sawan", "60"),
            ("Nakhon Si Thammarat", "80"),
            ("Nan", "55"),
            ("Narathiwat", "96"),
            ("Nong Bua Lamphu", "39"),
            ("Nong Khai", "43"),
            ("Nonthaburi", "12"),
            ("Pathum Thani", "13"),
            ("Pattani", "94"),
            ("Phang Nga", "82"),
            ("Phatthalung", "93"),
            ("Phayao", "56"),
            ("Phetchabun", "67"),
            ("Phetchaburi", "76"),
            ("Phichit", "66"),
            ("Phitsanulok", "65"),
            ("Phra Nakhon Si Ayutthaya", "14"),
            ("Phrae", "54"),
            ("Phuket", "83"),
            ("Prachinburi", "25"),
            ("Prachuap Khiri Khan", "77"),
            ("Ranong", "85"),
            ("Ratchaburi", "70"),
            ("Rayong", "21"),
            ("Roi Et", "45"),
            ("Sa Kaeo", "27"),
            ("Sakon Nakhon", "47"),
            ("Samut Prakan", "11"),
            ("Samut Sakhon", "74"),
            ("Samut Songkhram", "75"),
            ("Saraburi", "19"),
            ("Satun", "91"),
            ("Sing Buri", "17"),
            ("Sisaket", "33"),
            ("Songkhla", "90"),
            ("Sukhothai", "64"),
            ("Suphan Buri", "72"),
            ("Surat Thani", "84"),
            ("Surin", "32"),
            ("Tak", "63"),
            ("Trang", "92"),
            ("Trat", "23"),
            ("Ubon Ratchathani", "34"),
            ("Udon Thani", "41"),
            ("Uthai Thani", "61"),
            ("Uttaradit", "53"),
            ("Yala", "95"),
            ("Yasothon", "35"),
        ]

        created_count = 0
        for province_name, province_code in thai_provinces:
            _, created = Geography.objects.get_or_create(
                name=province_name,
                defaults={
                    "code": province_code,
                    "type": GeoTypes.STATE,
                    "parent_id": thailand,
                },
            )
            if created:
                created_count += 1

        self.stdout.write(
            f"Thai provinces: {created_count} created, {len(thai_provinces) - created_count} already existed"
        )

    def _populate_philippines(self, parent: Geography) -> None:
        """Populate Philippines and its provinces."""
        philippines, created = Geography.objects.get_or_create(
            name="Philippines",
            defaults={"code": "PH", "type": GeoTypes.COUNTRY, "parent_id": parent},
        )
        if created:
            self.stdout.write(f"Created country: {philippines.name}")
        else:
            self.stdout.write(f"Country already exists: {philippines.name}")

        philippine_provinces = [
            # Luzon - NCR
            ("Metro Manila", "NCR"),
            # Luzon - CAR
            ("Abra", "ABR"),
            ("Apayao", "APA"),
            ("Benguet", "BEN"),
            ("Ifugao", "IFU"),
            ("Kalinga", "KAL"),
            ("Mountain Province", "MOU"),
            # Luzon - Region I (Ilocos)
            ("Ilocos Norte", "ILN"),
            ("Ilocos Sur", "ILS"),
            ("La Union", "LUN"),
            ("Pangasinan", "PAN"),
            # Luzon - Region II (Cagayan Valley)
            ("Batanes", "BTN"),
            ("Cagayan", "CAG"),
            ("Isabela", "ISA"),
            ("Nueva Vizcaya", "NUV"),
            ("Quirino", "QUI"),
            # Luzon - Region III (Central Luzon)
            ("Aurora", "AUR"),
            ("Bataan", "BAN"),
            ("Bulacan", "BUL"),
            ("Nueva Ecija", "NUE"),
            ("Pampanga", "PAM"),
            ("Tarlac", "TAR"),
            ("Zambales", "ZMB"),
            # Luzon - Region IV-A (CALABARZON)
            ("Batangas", "BTG"),
            ("Cavite", "CAV"),
            ("Laguna", "LAG"),
            ("Quezon", "QUE"),
            ("Rizal", "RIZ"),
            # Luzon - Region IV-B (MIMAROPA)
            ("Marinduque", "MAD"),
            ("Occidental Mindoro", "MDC"),
            ("Oriental Mindoro", "MDR"),
            ("Palawan", "PLW"),
            ("Romblon", "ROM"),
            # Luzon - Region V (Bicol)
            ("Albay", "ALB"),
            ("Camarines Norte", "CAN"),
            ("Camarines Sur", "CAS"),
            ("Catanduanes", "CAT"),
            ("Masbate", "MAS"),
            ("Sorsogon", "SOR"),
            # Visayas - Region VI (Western Visayas)
            ("Aklan", "AKL"),
            ("Antique", "ANT"),
            ("Capiz", "CAP"),
            ("Guimaras", "GUI"),
            ("Iloilo", "ILI"),
            ("Negros Occidental", "NEC"),
            # Visayas - Region VII (Central Visayas)
            ("Bohol", "BOH"),
            ("Cebu", "CEB"),
            ("Negros Oriental", "NER"),
            ("Siquijor", "SIG"),
            # Visayas - Region VIII (Eastern Visayas)
            ("Biliran", "BIL"),
            ("Eastern Samar", "EAS"),
            ("Leyte", "LEY"),
            ("Northern Samar", "NSA"),
            ("Samar", "WSA"),
            ("Southern Leyte", "SLE"),
            # Mindanao - Region IX (Zamboanga Peninsula)
            ("Zamboanga del Norte", "ZAN"),
            ("Zamboanga del Sur", "ZAS"),
            ("Zamboanga Sibugay", "ZSI"),
            # Mindanao - Region X (Northern Mindanao)
            ("Bukidnon", "BUK"),
            ("Camiguin", "CAM"),
            ("Lanao del Norte", "LAN"),
            ("Misamis Occidental", "MSC"),
            ("Misamis Oriental", "MSR"),
            # Mindanao - Region XI (Davao)
            ("Davao de Oro", "COM"),
            ("Davao del Norte", "DAV"),
            ("Davao del Sur", "DAS"),
            ("Davao Occidental", "DAO"),
            ("Davao Oriental", "DAO"),
            # Mindanao - Region XII (SOCCSKSARGEN)
            ("Cotabato", "NCO"),
            ("Sarangani", "SAR"),
            ("South Cotabato", "SCO"),
            ("Sultan Kudarat", "SUK"),
            # Mindanao - Region XIII (Caraga)
            ("Agusan del Norte", "AGN"),
            ("Agusan del Sur", "AGS"),
            ("Dinagat Islands", "DIN"),
            ("Surigao del Norte", "SUN"),
            ("Surigao del Sur", "SUR"),
            # Mindanao - BARMM
            ("Basilan", "BAS"),
            ("Lanao del Sur", "LAS"),
            ("Maguindanao", "MAG"),
            ("Sulu", "SLU"),
            ("Tawi-Tawi", "TAW"),
        ]

        created_count = 0
        for province_name, province_code in philippine_provinces:
            _, created = Geography.objects.get_or_create(
                name=province_name,
                defaults={
                    "code": province_code,
                    "type": GeoTypes.STATE,
                    "parent_id": philippines,
                },
            )
            if created:
                created_count += 1

        self.stdout.write(
            f"Philippine provinces: {created_count} created, {len(philippine_provinces) - created_count} already existed"
        )
