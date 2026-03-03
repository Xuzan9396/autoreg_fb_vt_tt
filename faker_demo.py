from faker import Faker

# fake = Faker("fr_FR")
# for _ in range(5):
#     print(fake.name())


# fake = Faker("en_US")
fake = Faker("fr_FR")

for _ in range(5):
    print(fake.name(), "|", fake.address().replace("\n", ", "), "|", fake.ssn())