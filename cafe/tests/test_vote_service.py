import pytest

from cafe.services.vote_service import VoteService
from cafe.tests.factories import CafeFactory, UserFactory, CafeAttributeVoteFactory


@pytest.mark.django_db
class TestVoteServicePetAttributes:
    """測試 VoteService 對 pet_friendly / has_pet 屬性的投票與聚合"""

    def test_create_user_votes_pet_friendly(self):
        """pet_friendly 投票後，Cafe 欄位更新為多數決結果"""
        cafe = CafeFactory()
        user1 = UserFactory()
        user2 = UserFactory()
        user3 = UserFactory()

        # 三票 yes → 多數決 yes
        VoteService.create_user_votes(cafe.id, user1.id, {'pet_friendly': 'yes'})
        VoteService.create_user_votes(cafe.id, user2.id, {'pet_friendly': 'yes'})
        VoteService.create_user_votes(cafe.id, user3.id, {'pet_friendly': 'no'})

        cafe.refresh_from_db()
        assert cafe.pet_friendly == 'yes'

    def test_create_user_votes_has_pet(self):
        """has_pet 投票後，Cafe 欄位更新為多數決結果"""
        cafe = CafeFactory()
        user1 = UserFactory()
        user2 = UserFactory()

        VoteService.create_user_votes(cafe.id, user1.id, {'has_pet': 'no'})
        VoteService.create_user_votes(cafe.id, user2.id, {'has_pet': 'no'})

        cafe.refresh_from_db()
        assert cafe.has_pet == 'no'

    def test_create_user_votes_multiple_attributes(self):
        """同時投票 pet_friendly 和 has_pet"""
        cafe = CafeFactory()
        user = UserFactory()

        VoteService.create_user_votes(cafe.id, user.id, {
            'pet_friendly': 'yes',
            'has_pet': 'yes',
        })

        cafe.refresh_from_db()
        assert cafe.pet_friendly == 'yes'
        assert cafe.has_pet == 'yes'

    def test_unknown_votes_excluded_from_aggregation(self):
        """'unknown' 票不計入聚合"""
        cafe = CafeFactory()
        user1 = UserFactory()
        user2 = UserFactory()
        user3 = UserFactory()

        # 2 票 unknown（排除） + 1 票 yes → yes 勝出
        CafeAttributeVoteFactory(cafe=cafe, user=user1, attribute='pet_friendly', value='unknown', source='user')
        CafeAttributeVoteFactory(cafe=cafe, user=user2, attribute='pet_friendly', value='unknown', source='user')
        CafeAttributeVoteFactory(cafe=cafe, user=user3, attribute='pet_friendly', value='yes', source='user')

        VoteService.aggregate_and_update_cafe(cafe)

        cafe.refresh_from_db()
        assert cafe.pet_friendly == 'yes'

    def test_no_votes_does_not_change_field(self):
        """沒有投票時，Cafe 欄位不變"""
        cafe = CafeFactory(pet_friendly=None, has_pet=None)

        VoteService.aggregate_and_update_cafe(cafe)

        cafe.refresh_from_db()
        assert cafe.pet_friendly is None
        assert cafe.has_pet is None

    def test_majority_wins(self):
        """多數決：票數多的值勝出"""
        cafe = CafeFactory()
        users = [UserFactory() for _ in range(5)]

        # 3 票 maybe，2 票 yes → maybe 勝出
        for i, value in enumerate(['maybe', 'maybe', 'maybe', 'yes', 'yes']):
            CafeAttributeVoteFactory(cafe=cafe, user=users[i], attribute='has_pet', value=value, source='user')

        VoteService.aggregate_and_update_cafe(cafe)

        cafe.refresh_from_db()
        assert cafe.has_pet == 'maybe'
