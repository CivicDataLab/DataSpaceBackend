def get_graphql_type_fields_name(type_):
  return type_.__dict__["__dataclass_fields__"].keys()

def convert_to_graphql_type(db_model_object, graphql_type):
  fields = get_graphql_type_fields_name(graphql_type)
  return graphql_type(**{f: getattr(db_model_object, f) for f in fields})