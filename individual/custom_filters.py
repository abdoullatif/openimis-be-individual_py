import json
import logging
import re

from collections import namedtuple
from django.apps import apps
from django.db.models.query import QuerySet
from typing import List

from core.custom_filters import CustomFilterWizardInterface
from individual.apps import IndividualConfig
from individual.models import Individual, Group, GroupIndividual


logger = logging.getLogger(__name__)


class IndividualCustomFilterWizard(CustomFilterWizardInterface):

    OBJECT_CLASS = Individual

    def get_type_of_object(self) -> str:
        return self.OBJECT_CLASS.__name__

    def load_definition(self, tuple_type: type, **kwargs) -> List[namedtuple]:
        individual_schema = IndividualConfig.individual_schema
        additional_params = kwargs.get('additional_params', None)
        benefit_plan_id = additional_params.get("benefitPlan", None)
        if benefit_plan_id and 'social_protection' in apps.app_configs:
            from social_protection.models import BenefitPlan
            benefit_plan = BenefitPlan.objects.get(id=benefit_plan_id)
            if benefit_plan.beneficiary_data_schema and benefit_plan.beneficiary_data_schema != '{}':
                return self.__process_schema_and_build_tuple(benefit_plan.beneficiary_data_schema, tuple_type)
        if individual_schema:
            individual_schema_dict = json.loads(individual_schema)
            return self.__process_schema_and_build_tuple(individual_schema_dict, tuple_type)
        return []

    def apply_filter_to_queryset(self, custom_filters: List[namedtuple], query: QuerySet, relation=None) -> QuerySet:
        for filter_part in custom_filters:
            if isinstance(filter_part, dict):
                value_type = filter_part['type']
                value = filter_part['value']
                field = filter_part['field'] + '__' + filter_part['filter']
            else:
                try:
                    field, raw_value = filter_part.split("=", 1)
                    field, value_type = field.rsplit("__", 1)
                    value = raw_value
                except ValueError:
                    logger.error(f"Invalid filter format: {filter_part}")
                    continue

            value = value.get('name', '') if isinstance(value, dict) else self.__cast_value(value, value_type)
            filter_kwargs = {f"{relation}__json_ext__{field}" if relation else f"json_ext__{field}": value}
            query = query.filter(**filter_kwargs).distinct()
        return query

    def __process_schema_and_build_tuple(
            self,
            individual_schema: dict,
            tuple_type: type
    ) -> List[namedtuple]:
        tuples_with_definitions = []

        properties = individual_schema.get('properties', {})
        for key, value in properties.items():
            tuple_with_definition = tuple_type(
                field=key,
                filter=self.FILTERS_BASED_ON_FIELD_TYPE[value['type']],
                type=value['type'],
                referential=value['referential'] if 'referential' in value else None,
                typeLocation=value['typeLocation'] if 'typeLocation' in value else None
            )
            tuples_with_definitions.append(tuple_with_definition)

        else:
            logger.warning('Cannot retrieve definitions of filters based '
                            'on the provided schema due to either empty schema '
                            'or missing properties in schema file')

        return tuples_with_definitions

    def __cast_value(self, value: str, value_type: str):
        if value_type == 'integer':
            return int(value)
        elif value_type == 'numeric':
            return float(value)
        elif value_type == 'boolean':
            cleaned_value = self.__remove_unexpected_chars(value)
            return cleaned_value.lower() == 'true'
        elif value_type == 'date':
            # parser avec datetime.strptime si besoin
            return value
        elif value_type == 'string':
            # Si c'est un JSON -> essayer de parser
            try:
                obj = json.loads(value)
                if isinstance(obj, dict):
                    return obj.get("name", "")  # récupère uniquement le "name"
                return str(obj)
            except Exception:
                return str(value).strip('"')

        return value

    def __remove_unexpected_chars(self, string: str):
        pattern = r'[^\w\s]'  # Remove any character that is not alphanumeric or whitespace

        # Use re.sub() to remove the unwanted characters
        cleaned_string = re.sub(pattern, '', string)

        return cleaned_string


class GroupCustomFilterWizard(IndividualCustomFilterWizard):

    OBJECT_CLASS = Group


class GroupIndividualCustomFilterWizard(IndividualCustomFilterWizard):

    OBJECT_CLASS = GroupIndividual
