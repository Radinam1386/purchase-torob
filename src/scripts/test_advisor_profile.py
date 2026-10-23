"""Offline checks for the structured, editable shopping consultation profile."""
import unittest
from langchain_core.messages import HumanMessage, ToolMessage
from src.core.agent import ShoppingAgent, _apply_constraints, _update_conversation
from src.core.contract import ConversationState


def turn(text, previous=None):
    return ShoppingAgent._advisor_gate({'messages':[HumanMessage(content=text)],
                                      'conversation':previous['conversation'] if previous else {}})


class AdvisorProfileTests(unittest.TestCase):
    def test_headphone_preferences_and_hard_constraints_are_structured(self):
        result=turn('هدفون روگوشی برای موسیقی تا ۳ میلیون، فقط بی سیم، حذف نویز و راحتی مهمه')
        profile=result['conversation']['preferences'].get('searchProfile', {})
        self.assertEqual(profile.get('category'),'هدفون')
        self.assertEqual(profile.get('budget'),3_000_000)
        self.assertEqual(profile.get('importantPreferences',{}).get('connection'),'بی‌سیم')
        self.assertEqual(profile.get('hardConstraints',{}).get('connection'),'بی‌سیم')
        self.assertIn('روگوشی',result['clarification_question'])
        self.assertIn('حذف نویز',result['clarification_question'])
        self.assertEqual(profile.get('stage'),'ready_to_search')

    def test_budget_question_collects_category_specific_preferences_without_loop(self):
        examples=[('هدفون برای موسیقی','روگوشی'),('لپ تاپ برای کار','حمل'),
                  ('کفش برای پیاده روی','سایز'),('گوشی برای روزمره','دوربین')]
        for text, expected in examples:
            with self.subTest(text=text):
                initial=turn(text)
                self.assertIn(expected,initial['clarification_question'])
                ready=turn('تا ۵ میلیون',initial)
                self.assertIn('خلاصه ترجیحات',ready['clarification_question'])
                self.assertTrue(ready['conversation']['preferences']['searchProfile']['unknownInformation'])

    def test_programming_in_initial_request_is_known_and_portability_persists(self):
        result=turn('لپ تاپ برای برنامه نویسی تا ۵۰ میلیون سبک با باتری خوب')
        profile=result['conversation']['preferences'].get('searchProfile',{})
        self.assertIn('برنامه نویسی',str(profile.get('use')))
        self.assertIn('portability',profile.get('importantPreferences',{}))
        self.assertIn('battery',profile.get('importantPreferences',{}))
        self.assertIn('خلاصه ترجیحات',result['clarification_question'])

    def test_incompatible_budget_bounds_need_one_clarification_even_for_search(self):
        result=turn('هدفون برای موسیقی حداکثر ۲ میلیون و حداقل ۵ میلیون، جستجو کن')
        self.assertIn('بودجه',result.get('clarification_question',''))
        self.assertEqual(result.get('clarification_question','').count('؟'),1)
        profile=result['conversation']['preferences'].get('searchProfile',{})
        self.assertTrue(profile.get('contradictions'))
        self.assertEqual(profile.get('stage'),'clarifying_requirements')
        unresolved=turn('بله',result)
        self.assertIn('بودجه',unresolved.get('clarification_question',''))
        unrelated=turn('سایز ۴۲',unresolved)
        self.assertIn('budget',unrelated['conversation']['preferences']['searchProfile']['contradictions'])
        corrected=turn('اصلاح می کنم بودجه حداکثر ۳ میلیون',unresolved)
        self.assertEqual(corrected['conversation']['budget'],3_000_000)
        self.assertFalse(corrected['conversation']['preferences']['searchProfile']['contradictions'])
        self.assertIn('خلاصه ترجیحات',corrected['clarification_question'])

    def test_mutually_exclusive_connection_then_correction(self):
        result=turn('هدفون برای موسیقی تا ۳ میلیون با سیم و فقط بی سیم')
        self.assertTrue(result['conversation']['preferences'].get('searchProfile',{}).get('contradictions'))
        self.assertEqual(result.get('clarification_question','').count('؟'),1)
        corrected=turn('فقط بی سیم می خوام',result)
        self.assertEqual(corrected['conversation']['preferences']['searchProfile']['importantPreferences']['connection'],'بی‌سیم')
        self.assertIn('خلاصه ترجیحات',corrected['clarification_question'])

    def test_summary_edit_overrides_prior_preference_and_budget(self):
        initial=turn('هدفون روگوشی برای موسیقی تا ۳ میلیون بی سیم')
        corrected=turn('نه، ایرباد باسیم تا ۲ میلیون',initial)
        profile=corrected['conversation']['preferences'].get('searchProfile',{})
        self.assertEqual(profile.get('importantPreferences',{}).get('type'),'ایرباد')
        self.assertEqual(profile.get('importantPreferences',{}).get('connection'),'باسیم')
        self.assertEqual(profile.get('budget'),2_000_000)
        self.assertNotIn('clarifying_requirements',profile.get('stage',''))

    def test_quick_search_records_unknown_preferences_and_assumptions(self):
        result=turn('گوشی می خوام سریع جستجو کن')
        self.assertNotIn('clarification_question',result)
        profile=result['conversation']['preferences'].get('searchProfile',{})
        self.assertEqual(profile.get('stage'),'searching')
        self.assertIn('دوربین',profile.get('unknownInformation',[]))
        self.assertTrue(result['conversation']['preferences']['_advisor']['assumptions'])

    def test_selected_product_stage_and_profile_survive_contact_turn(self):
        initial=turn('هدفون برای موسیقی تا ۳ میلیون')
        initial['conversation']['selectedProductId']='p1'
        initial['conversation']['preferences']['_advisor']['status']='prepare_contact'
        followup=turn('بله',initial)
        self.assertEqual(followup['conversation']['preferences']['searchProfile']['stage'],'prepare_contact')
        self.assertNotIn('clarification_question',followup)
        contact=turn('برای تماس آماده کن',followup)
        self.assertEqual(contact['conversation']['preferences']['searchProfile']['use'],'موسیقی')

    def test_requirement_edits_clear_selected_product_and_refresh_profile(self):
        initial=turn('هدفون برای موسیقی فقط بی سیم تا ۳ میلیون')
        initial['conversation'].update(selectedProductId='p1',selectedShopIds=['s1'],selectedOfferIds=['o1'])
        initial['conversation']['preferences']['_advisor']['status']='prepare_contact'
        result=turn('هدفون برای ورزش میخوام فقط باسیم تا ۲ میلیون',initial)
        profile=result['conversation']['preferences']['searchProfile']
        self.assertEqual(profile['use'],'ورزش')
        self.assertEqual(profile['importantPreferences']['connection'],'باسیم')
        self.assertEqual(profile['hardConstraints']['connection'],'باسیم')
        self.assertEqual(profile['hardConstraints']['budgetMax'],2_000_000)
        self.assertIsNone(result['conversation']['selectedProductId'])
        self.assertEqual(result['conversation']['selectedShopIds'],[])
        self.assertEqual(result['conversation']['selectedOfferIds'],[])
        self.assertEqual(profile['stage'],'ready_to_search')
        confirmed=turn('بله',result)
        self.assertEqual(confirmed['conversation']['preferences']['searchProfile']['stage'],'searching')

    def test_selected_product_does_not_skip_contradiction_clarification(self):
        initial=turn('هدفون برای موسیقی تا ۳ میلیون')
        initial['conversation'].update(selectedProductId='p1',selectedShopIds=['s1'],selectedOfferIds=['o1'])
        result=turn('هدفون با سیم و فقط بی سیم',initial)
        self.assertIn('connection',result['conversation']['preferences']['searchProfile']['contradictions'])
        self.assertIn('clarification_question',result)
        self.assertIsNone(result['conversation']['selectedProductId'])

    def test_contact_commands_preserve_profile_and_all_selections(self):
        initial=turn('هدفون برای موسیقی فقط بی سیم تا ۳ میلیون')
        initial['conversation'].update(selectedProductId='p1',selectedShopIds=['s1'],selectedOfferIds=['o1'])
        initial['conversation']['preferences']['_advisor']['status']='prepare_contact'
        for message in ['بله','برای تماس آماده کن','با فروشنده تماس بگیر','وضعیت استعلام را بگو']:
            with self.subTest(message=message):
                result=turn(message,initial)
                profile=result['conversation']['preferences']['searchProfile']
                self.assertEqual(profile['use'],'موسیقی')
                self.assertEqual(profile['importantPreferences']['connection'],'بی‌سیم')
                self.assertEqual(profile['stage'],'prepare_contact')
                self.assertEqual(result['conversation']['selectedProductId'],'p1')
                self.assertEqual(result['conversation']['selectedShopIds'],['s1'])
                self.assertEqual(result['conversation']['selectedOfferIds'],['o1'])
                self.assertNotIn('clarification_question',result)

    def test_minimum_price_is_not_misread_as_maximum_budget(self):
        result=turn('هدفون برای موسیقی حداقل ۳ میلیون')
        self.assertIsNone(result['conversation'].get('budget'))
        self.assertIn('بودجه',result.get('clarification_question',''))
        self.assertEqual(result['conversation']['preferences']['searchProfile']['hardConstraints']['budgetMin'],3_000_000)

    def test_finished_search_updates_profile_stage(self):
        initial=turn('هدفون برای موسیقی تا ۳ میلیون جستجو کن')
        state=ConversationState.model_validate(initial['conversation'])
        _update_conversation(state,{'conversation':{},'messages':[
            ToolMessage(content='{"data":[]}',tool_call_id='s1',name='search_products')]})
        self.assertEqual(state.preferences['searchProfile']['stage'],'showing_results')

    def test_conflicting_budget_does_not_replace_accepted_budget(self):
        state=ConversationState(budget=4_000_000)
        _apply_constraints(state,'حداکثر ۲ میلیون ولی حداقل ۵ میلیون')
        self.assertEqual(state.budget,4_000_000)


if __name__=='__main__':
    unittest.main()
