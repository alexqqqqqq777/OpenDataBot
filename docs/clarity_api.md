# Clarity API Documentation (local copy)

Base URL: `https://clarity-project.info/api`
Docs: https://github.com/the-clarity-project/api

## Endpoints

### Юридичні особи та ФОП
| Endpoint | Опис | Вартість |
|----------|------|----------|
| `edr.info/{edrpou}` | Інфо з ЄДР (founders, beneficiaries, signers, predecessors, branches, vat, tax_debt, owned.vehicle) | 1 запит |
| `edr.search?q=...` | Пошук ю/о та ФОП | 1 |
| `edr.changes` | Стрічка змін | 1 |
| `edrpou.history/{edrpou}` | Історія змін з ЄДР | 1 |
| `edr.info/{edrpou}/licenses` | Ліцензії | 1 |
| `edr.info/{edrpou}/persons` | Пов'язані особи (Type: director, beneficiary, signer, founder, accountant, contact) | 1 |
| `edr.info/{edrpou}/treasury` | Транзакції Казначейства (bank_accounts, by_date stats) | 1 |
| `edr.info/{edrpou}/used-vehicles` | Автотранспорт у КОРИСТУВАННІ (LicenseStatus, VehicleType/Num/Model/Year, VINCode) | 1 |
| `edr.finances/{edrpou}?year=&month=` | Фінансові звіти (meta + data forms) | 1 |
| `edr.history/{edrpou}` | Історія змін Prozorro | 1 |
| `edr.relations/{edrpou}` | ЗВ'ЯЗКИ! (Person, Phone, Email, Address, Founder → edrs з ЄДРПОУ) | 1 |

### Власність
| Endpoint | Опис | Вартість |
|----------|------|----------|
| `vehicles.list/{code}` | Автотранспорт у ВЛАСНОСТІ (brand, model, makeYear, capacity, color, kind, body, fuel, ownWeight, totalWeight) | 1 |
| `realty.list?code=&name=` | Нерухомість (потребує ідентифікації) | 1 |

### Податки
| Endpoint | Опис |
|----------|------|
| `tax.info/{edrpou}` | Платник податків (vat, single_tax, tax_debt) |

### ФОП
| Endpoint | Опис |
|----------|------|
| `fop.byname?q=ПІБ` | Пошук ФОП за ПІБ |
| `fop.bycode/{code}` | ФОП за РНОКПП |
| `fop.info/{id}` | ФОП за внутрішнім ID |

### Фізичні особи
| Endpoint | Опис |
|----------|------|
| `persons.search?q=ПІБ` | Пошук → hash |
| `persons.info/{hash}` | Інфо: edrs (всі компанії+ролі), otherpersons, securityInfo |

### Закупівлі
| Endpoint | Опис |
|----------|------|
| `tender.search` | Пошук закупівель |
| `tender.ids` | Пошук ID закупівель |

### Інше
| Endpoint | Опис |
|----------|------|
| `passport.check/{number}` | Перевірка паспорта |

---

## Ключові структури відповідей

### edr.info → edr_data
- founders[]: Name, Edrpou, Country, CapitalPart
- beneficiaries[]: Name, Country
- signers[]: Name, Type (director/signer), Inn, Limit
- predecessors[]: RelatedName, RelatedEdr, Type (predecessor/assignee)
- branches[]: Edrpou, Name
- owned.vehicle: кількість авто

### edr.info/persons → list[]
- Name, Hash, Type (director/beneficiary/signer/founder/accountant/contact/other)
- Actual (1=діючий), SourceType (edr/fin-report/prozorro-sale/inspection)

### edr.relations → relations + edrs
- relations: {Person[], Phone[], Email[], Address[], Founder[]}
- edrs: {code: {Name, Edr}}

### vehicles.list → vehicles[]
- brand, model, makeYear, capacity, color, kind, body, purpose, fuel
- ownWeight, totalWeight, operName, depName, dreg
- БЕЗ номера та VIN-коду

### edr.info/used-vehicles → vehicles[]
- VehicleNum, VehicleModel, VehicleVendor, VehicleYear, VehicleType
- VINCode, LicenseStatus, LicenseStart, LicenseEnd
- VehicleLoad, VehicleSeats

### persons.info/{hash} → list.{hash}
- name, hash
- edrs: {role_group: [{Edr, EdrName, Type, Actual}]}
- otherpersons, securityInfo
