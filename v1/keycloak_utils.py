from keycloak import KeycloakAdmin
from keycloak import KeycloakOpenIDConnection
from decouple import config

def __create_admin() -> KeycloakAdmin:
    print(config("KEYCLOAK_SERVER_URL"))
    print(config("KEYCLOAK_API_CLIENT_ID"))
    print(config("KEYCLOAK_REALM"))
    print(config("KEYCLOAK_USER_NAME"))
    print(config("KEYCLOAK_PASSWORD"))
    keycloak_connection = KeycloakOpenIDConnection(server_url=config("KEYCLOAK_SERVER_URL"),
                                    #realm_name=settings.KEYCLOAK_REALM,
                                    user_realm_name="master",
                                    client_id=config("KEYCLOAK_API_CLIENT_ID"),
                                    #client_id="admin-cli",
                                    #client_secret_key=settings.KEYCLOAK_API_CLIENT_SECRET,
                                    realm_name=config("KEYCLOAK_REALM"),
                                    username=config("KEYCLOAK_USER_NAME"),
                                    password=config("KEYCLOAK_PASSWORD"),                                    
                                    verify=True
                                    )
    keycloak_admin = KeycloakAdmin(connection=keycloak_connection)
    return keycloak_admin

def register_user_with_keycloak(user_data):
    print(config("KEYCLOAK_SERVER_URL"))    
    keycloak_admin = __create_admin()
    print(user_data)
    ur = keycloak_admin.create_user(user_data)
    print(keycloak_admin.users_count())
    print(ur)
    #response = keycloak_admin.send_verify_email(user_id="user-id-keycloak")
    
def get_user(email: str):
    keycloak_admin = __create_admin()
    users = keycloak_admin.get_users({"email":email})
    return users

def update_by_phone_number(phone_number, email, epassport_number):
    keycloak_admin = __create_admin()
    users = get_user_by_phone(phone_number)
    if not users:
        pass
    user = users[0]
    user['attributes']['epassportNumber'] = epassport_number
    updated_attributes = {  
                           'firstName': user['firstName'],
                           'lastName': user['lastName'],
                           'email': email,
                           'attributes': user['attributes'],
                           'username': epassport_number,
                           'requiredActions': [], 
                           'emailVerified': True,
                           'enabled': True 
                        }
    keycloak_admin.update_user(user['id'], updated_attributes)
    
def get_user_by_phone(phone_number: str):
    keycloak_admin = __create_admin()
    print(phone_number)
    print("keycloak file")
    users = keycloak_admin.get_users({"q":f"phoneNumber:{phone_number}"})
    print(f"users are: {users}") 
    return users

def update_epassport_number(email, epassport_number):
    keycloak_admin = __create_admin()
    users = keycloak_admin.get_users({"email":email})
    if not users:
        pass
    user = users[0]
    updated_attributes = { 'username': epassport_number }
    keycloak_admin.update_user(user['id'], updated_attributes)


def enable(email, epassport_number):
    keycloak_admin = __create_admin()
    users = keycloak_admin.get_users({"email":email})
    if not users:
        pass
    user = users[0]
    updated_attributes = {
        "enabled": True,
        "emailVerified": True,
        'requiredActions': [],
        'username': epassport_number,
    }
    keycloak_admin.update_user(user['id'], updated_attributes)
