import factory
from factory.alchemy import SQLAlchemyModelFactory
from app.models.schemas import UserCreate, UserResponse
from app.database.models import User
from faker import Faker

fake = Faker()

class UserCreateFactory(factory.Factory):
    """用户创建工厂"""
    class Meta:
        model = UserCreate
    
    email = factory.LazyAttribute(lambda _: fake.email())
    password = factory.LazyAttribute(lambda _: fake.password())
    name = factory.LazyAttribute(lambda _: fake.name())

class UserResponseFactory(factory.Factory):
    """用户响应工厂"""
    class Meta:
        model = UserResponse
    
    id = factory.Sequence(lambda n: n)
    email = factory.LazyAttribute(lambda _: fake.email())
    name = factory.LazyAttribute(lambda _: fake.name())
