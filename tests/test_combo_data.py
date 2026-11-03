import copy
import json
import tempfile
import unittest
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

from mhwilds_optimizer.combo_data import ComboDataError, VerificationStatus, load_combo


class ComboDataTests(unittest.TestCase):
    def setUp(self) -> None:
        source = (
            Path(__file__).parents[1]
            / "mhwilds_optimizer"
            / "data"
            / "combos"
            / "dual_blades.json"
        )
        self.valid_payload = json.loads(source.read_text(encoding="utf-8"))

    def write_payload(self, root: str, payload: object) -> Path:
        path = Path(root) / "combo.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_loads_demon_dance_hit_sequences_as_decimal(self) -> None:
        combo = load_combo()

        self.assertEqual(combo.id, "dual_blades:demon_dance_1_3")
        self.assertEqual(combo.weapon_type, "dual_blades")
        self.assertEqual(combo.verification_status, VerificationStatus.CROSS_CHECKED)
        self.assertEqual(len(combo.hits), 27)
        self.assertEqual(
            [hit.motion_value for hit in combo.hits],
            [
                Decimal(str(value))
                for value in (
                    18, 18, 6, 6, 10, 10, 4, 4, 20, 20, 11, 11,
                    16, 16, 6, 25,
                    22, 8, 5, 22, 5, 14, 18, 8, 18, 36, 36,
                )
            ],
        )
        self.assertEqual(
            [hit.element_modifier for hit in combo.hits],
            [
                Decimal(str(value))
                for value in (
                    1, 1, 0.6, 0.6, 0.6, 0.6, 0.8, 0.8, 0.8, 0.8, 0.8, 0.8,
                    0.6, 0.6, 0.8, 0.8,
                    0.6, 0.6, 0.6, 0.6, 0.8, 0.8, 0.8, 0.8, 0.8, 0.8, 0.8,
                )
            ],
        )
        self.assertEqual(
            Counter(hit.move_id for hit in combo.hits),
            {"demon_dance_1": 12, "demon_dance_2": 4, "demon_dance_3": 11},
        )
        self.assertEqual([hit.index for hit in combo.hits], list(range(1, 28)))
        move_indexes: defaultdict[str, list[int]] = defaultdict(list)
        for hit in combo.hits:
            move_indexes[hit.move_id].append(hit.move_hit_index)
        self.assertEqual(move_indexes["demon_dance_1"], list(range(1, 13)))
        self.assertEqual(move_indexes["demon_dance_2"], list(range(1, 5)))
        self.assertEqual(move_indexes["demon_dance_3"], list(range(1, 12)))
        self.assertEqual({hit.damage_type for hit in combo.hits}, {"sever"})

        self.assertEqual(
            {source.url for source in combo.sources},
            {
                "https://kuroyonhon.com/mhwilds/memo/6.php",
                "https://macarongamemo.com/entry/mhwilds-dual_blades-motion",
                "https://macarongamemo.com/entry/mhwilds-damage_calculation",
                "https://kuroyonhon.com/mhwilds/memo/21.php",
                "https://steamcommunity.com/app/2246340/allnews/",
            },
        )
        self.assertTrue(all(source.supports for source in combo.sources))

    def test_rejects_unknown_combo_id(self) -> None:
        with self.assertRaisesRegex(ComboDataError, "missing:combo"):
            load_combo("missing:combo")

    def test_rejects_malformed_combo_data_with_field_context(self) -> None:
        cases = []

        missing_hit = copy.deepcopy(self.valid_payload)
        missing_hit["combos"][0]["hits"].pop()
        cases.append(("missing hit", missing_hit, "hits"))

        duplicate_index = copy.deepcopy(self.valid_payload)
        duplicate_index["combos"][0]["hits"][1]["index"] = 1
        cases.append(("duplicate index", duplicate_index, "index"))

        fractional_index = copy.deepcopy(self.valid_payload)
        fractional_index["combos"][0]["hits"][0]["index"] = 1.5
        cases.append(("fractional index", fractional_index, "index"))

        wrong_move_count = copy.deepcopy(self.valid_payload)
        wrong_move_count["combos"][0]["hits"][11]["move_id"] = "demon_dance_2"
        cases.append(("wrong move count", wrong_move_count, "move_id"))

        nonpositive_motion = copy.deepcopy(self.valid_payload)
        nonpositive_motion["combos"][0]["hits"][0]["motion_value"] = 0
        cases.append(("nonpositive motion", nonpositive_motion, "motion_value"))

        nonpositive_element = copy.deepcopy(self.valid_payload)
        nonpositive_element["combos"][0]["hits"][0]["element_modifier"] = 0
        cases.append(("nonpositive element", nonpositive_element, "element_modifier"))

        wrong_damage_type = copy.deepcopy(self.valid_payload)
        wrong_damage_type["combos"][0]["hits"][0]["damage_type"] = "blunt"
        cases.append(("wrong damage type", wrong_damage_type, "damage_type"))

        missing_support = copy.deepcopy(self.valid_payload)
        missing_support["sources"][0]["supports"] = []
        cases.append(("missing support", missing_support, "supports"))

        bad_status = copy.deepcopy(self.valid_payload)
        bad_status["verification_status"] = "trusted"
        cases.append(("bad status", bad_status, "verification_status"))

        bad_schema = copy.deepcopy(self.valid_payload)
        bad_schema["schema_version"] = 2
        cases.append(("bad schema", bad_schema, "schema_version"))

        duplicate_combo = copy.deepcopy(self.valid_payload)
        duplicate_combo["combos"].append(copy.deepcopy(duplicate_combo["combos"][0]))
        cases.append(("duplicate combo", duplicate_combo, "id"))

        bad_date = copy.deepcopy(self.valid_payload)
        bad_date["sources"][0]["checked_at"] = "not-a-date"
        cases.append(("bad date", bad_date, "checked_at"))

        missing_top_level = copy.deepcopy(self.valid_payload)
        del missing_top_level["game_version"]
        cases.append(("missing top level", missing_top_level, "game_version"))

        with tempfile.TemporaryDirectory() as temporary_directory:
            for name, payload, context in cases:
                with self.subTest(name=name):
                    path = self.write_payload(temporary_directory, payload)
                    with self.assertRaisesRegex(ComboDataError, context):
                        load_combo(path=path)


if __name__ == "__main__":
    unittest.main()
