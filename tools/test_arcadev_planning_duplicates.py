"""Generic overlapping-feature regression; no production authority input."""

import unittest

from arcadev import IdeaIntake, IdeaFinalization, IdeaPlanHandoff, ProjectMetadata, generate_baseline_plan
from tools.test_arcadev_idea_plan_handoff import _intent


def overlapping_handoff(features):
    values = ("Delivery Console", "web_application", "A delivery console", "operators",
              "Manage deliveries", "Desktop web", "Email/password", "No integrations",
              "Managed cloud", *features)
    transcript = "; ".join(sorted(values))
    def item(value):
        return _intent(value, transcript, scalar=True)
    intake = IdeaIntake.create(
        original_user_request=transcript, proposed_project_name=item(values[0]),
        project_type=item(values[1]), product_description=item(values[2]),
        target_users=[item(values[3])], primary_goal=item(values[4]),
        platform_targets=[item(values[5])], authentication_requirements=[item(values[6])],
        integration_requirements=[item(values[7])], deployment_requirements=[item(values[8])],
        requested_features=[item(value) for value in features],
    )
    finalization = IdeaFinalization.start(intake)
    return IdeaPlanHandoff.create(finalization.to_project(
        metadata=ProjectMetadata.create(created_at="2026-09-10T08:00:00Z")), finalization)


class PlanningDuplicatesTest(unittest.TestCase):
    def test_overlapping_features_merge_questions_and_risks_without_losing_sources(self):
        for features in (("asset upload", "asset download"),
                         ("build submission", "build history"),
                         ("publishing review", "publishing history")):
            with self.subTest(features=features):
                handoff = overlapping_handoff(features)
                plan = generate_baseline_plan(handoff)
                self.assertEqual(plan.canonical_json(), generate_baseline_plan(
                    overlapping_handoff(tuple(reversed(features)))).canonical_json())
                self.assertEqual(len(plan.open_planning_questions), 1)
                question = plan.open_planning_questions[0]
                self.assertEqual(set(question.source_requirements), set(features))
                self.assertTrue(question.blocking)
                self.assertFalse(plan.readiness.ready_for_architecture)
                if "asset" not in features[0]:
                    self.assertEqual(len(plan.risks), 1)
                    self.assertEqual(set(plan.risks[0].risk.source_requirements), set(features))
                    self.assertEqual(set(plan.risks[0].mitigation.source_requirements), set(features))


if __name__ == "__main__":
    unittest.main()
