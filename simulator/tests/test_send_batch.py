import unittest

from send_batch import classify_response


class BatchConfirmationTests(unittest.TestCase):
    def test_reports_each_outcome_and_rejects_incomplete_confirmations(self):
        identity = {"device_id": "test", "boot_id": "boot", "sequence_number": 0}
        accepted = identity | {"outcome": "accepted"}
        rejected = identity | {"outcome": "rejected", "reason": "invalid_unit"}
        self.assertEqual(
            classify_response(
                [identity, identity], {"batch_id": "b", "results": [accepted, rejected]}
            ),
            ["accepted", "rejected:invalid_unit"],
        )
        for results in (
            [],
            [accepted, accepted],
            [None],
            [accepted | {"device_id": "wrong"}],
            [accepted | {"outcome": "unknown"}],
            [accepted | {"reason": "invalid_unit"}],
            [identity | {"outcome": "rejected"}],
        ):
            with self.subTest(results=results), self.assertRaises(ValueError):
                classify_response([identity], {"batch_id": "b", "results": results})
