from keycloak_utils import get_user_by_phone, get_user

e_user = get_user("sri.paramesha@koogle.sk")
print(e_user)
p_user = get_user_by_phone("+919901424924")
print(p_user)
