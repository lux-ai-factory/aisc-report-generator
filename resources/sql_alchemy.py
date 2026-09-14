import enum
from typing import List, Optional
from sqlalchemy import (
    create_engine, Column, ForeignKey, Table, Text, Boolean, String, Date, 
    Time, DateTime, Float, Integer, Enum
)
from sqlalchemy.ext.declarative import AbstractConcreteBase
from sqlalchemy.orm import (
    column_property, DeclarativeBase, Mapped, mapped_column, relationship
)
from datetime import datetime as dt_datetime, time as dt_time, date as dt_date

class Base(DeclarativeBase):
    pass

# Definitions of Enumerations
class DatasetType(enum.Enum):
    Validation = "Validation"
    Test = "Test"
    Training = "Training"

class UserRole(enum.Enum):
    tester = "tester"
    admin = "admin"
    viewer = "viewer"

class TagsTargetSystem(enum.Enum):
    AI_Safety_and_Governance = "AI_Safety_and_Governance"
    Knowledge_and_Retrival = "Knowledge_and_Retrival"
    Audio = "Audio"
    Tabular_and_Structured_Data = "Tabular_and_Structured_Data"
    Computer_Vision = "Computer_Vision"
    Recommendation_and_Personalization = "Recommendation_and_Personalization"
    Multimodal = "Multimodal"
    Decision_and_Optimization = "Decision_and_Optimization"
    Agents_and_Agentic_Systems = "Agents_and_Agentic_Systems"
    Reinforcement_Learning_and_Control = "Reinforcement_Learning_and_Control"
    Natural_Language_Processing = "Natural_Language_Processing"
    Emerging_Other = "Emerging_Other"
    Predictive_and_Analytical_AI = "Predictive_and_Analytical_AI"

class TagsSector(enum.Enum):
    Environment = "Environment"
    Trade = "Trade"
    Inclusive_development = "Inclusive_development"
    Agriculture = "Agriculture"
    Education = "Education"
    Innovation = "Innovation"
    Investment = "Investment"
    Defence = "Defence"
    Health = "Health"
    Competition = "Competition"
    Economz = "Economz"

class VerificationType(enum.Enum):
    Case_1 = "Case_1"
    Case_3 = "Case_3"
    Case_2 = "Case_2"

class TagsVerificationTarget(enum.Enum):
    Accountability = "Accountability"
    Transparency = "Transparency"
    Societal_and_enviornmanetal_wellbeing = "Societal_and_enviornmanetal_wellbeing"
    Technical_Robustness_and_Saftey = "Technical_Robustness_and_Saftey"
    Risk_management = "Risk_management"
    Diversity_Nondiscrimination_and_Fairness = "Diversity_Nondiscrimination_and_Fairness"
    Privacy_and_Data_Governance = "Privacy_and_Data_Governance"
    Human_Agency_and_Oversight = "Human_Agency_and_Oversight"

class LicensingType(enum.Enum):
    Open_Source = "Open_Source"
    Proprietary = "Proprietary"

class ProjectStatus(enum.Enum):
    Ready = "Ready"
    Created = "Created"
    Closed = "Closed"
    Archived = "Archived"
    Pending = "Pending"

class EvaluationStatus(enum.Enum):
    Custom = "Custom"
    Pending = "Pending"
    Archived = "Archived"
    Processing = "Processing"
    Done = "Done"


# Tables definition for many-to-many relationships
aisystem_dataset = Table(
    "aisystem_dataset",
    Base.metadata,
    Column("models", ForeignKey("aisystem.id"), primary_key=True),
    Column("dataset", ForeignKey("dataset.id"), primary_key=True),
)
evaluation_element = Table(
    "evaluation_element",
    Base.metadata,
    Column("ref", ForeignKey("element.id"), primary_key=True),
    Column("eval", ForeignKey("evaluation.id"), primary_key=True),
)
metriccategory_metric = Table(
    "metriccategory_metric",
    Base.metadata,
    Column("metrics", ForeignKey("metric.id"), primary_key=True),
    Column("category", ForeignKey("metriccategory.id"), primary_key=True),
)
derived_metric = Table(
    "derived_metric",
    Base.metadata,
    Column("baseMetric", ForeignKey("metric.id"), primary_key=True),
    Column("derivedBy", ForeignKey("derived.id"), primary_key=True),
)
datashape_feature = Table(
    "datashape_feature",
    Base.metadata,
    Column("f_date", ForeignKey("feature.id"), primary_key=True),
    Column("date", ForeignKey("datashape.id"), primary_key=True),
)

# Tables definition
class test_catalog(Base):
    __tablename__ = "test_catalog"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    brief_description: Mapped[str] = mapped_column(String(100))
    dimension: Mapped[str] = mapped_column(String(100))

class landing_kpi(Base):
    __tablename__ = "landing_kpi"
    id: Mapped[int] = mapped_column(primary_key=True)
    partners: Mapped[int] = mapped_column(Integer)
    total_investment: Mapped[int] = mapped_column(Integer)
    focus_areas: Mapped[int] = mapped_column(Integer)
    entities: Mapped[int] = mapped_column(Integer)

class Comments(Base):
    __tablename__ = "comments"
    id: Mapped[int] = mapped_column(primary_key=True)
    text: Mapped[str] = mapped_column(String(10000))
    timeStamp: Mapped[dt_datetime] = mapped_column(DateTime)
    page_slug: Mapped[str] = mapped_column(String(100))
    parent_id: Mapped[int] = mapped_column(Integer)
    avatar_url: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[dt_datetime] = mapped_column(DateTime)
    updated_at: Mapped[dt_datetime] = mapped_column(DateTime)
    is_deleted: Mapped[bool] = mapped_column(Boolean)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"))

class User(Base):
    __tablename__ = "user"
    id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(100))
    last_login: Mapped[dt_datetime] = mapped_column(DateTime)
    email: Mapped[str] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[dt_datetime] = mapped_column(DateTime)
    user_id: Mapped[str] = mapped_column(String(100))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole))

class LegalRequirement(Base):
    __tablename__ = "legalrequirement"
    id: Mapped[int] = mapped_column(primary_key=True)
    legal_ref: Mapped[str] = mapped_column(String(100))
    standard: Mapped[str] = mapped_column(String(100))
    principle: Mapped[str] = mapped_column(String(100))
    project_1_id: Mapped[int] = mapped_column(ForeignKey("project.id"))

class Tools_catalogue(Base):
    __tablename__ = "tools_catalogue"
    id: Mapped[int] = mapped_column(primary_key=True)
    reviewed_at: Mapped[dt_datetime] = mapped_column(DateTime)
    created_at: Mapped[dt_datetime] = mapped_column(DateTime)
    slug: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(100))
    version: Mapped[str] = mapped_column(String(100))
    licensing: Mapped[LicensingType] = mapped_column(Enum(LicensingType))
    status: Mapped[str] = mapped_column(String(100))
    submitted_by: Mapped[str] = mapped_column(String(100))
    storage_path: Mapped[str] = mapped_column(String(100))
    reviewed_by: Mapped[str] = mapped_column(String(100))

class Datashape(Base):
    __tablename__ = "datashape"
    id: Mapped[int] = mapped_column(primary_key=True)
    accepted_target_values: Mapped[str] = mapped_column(String(100))

class Tags(Base):
    __tablename__ = "tags"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(100))
    label: Mapped[str] = mapped_column(String(100))
    section: Mapped[str] = mapped_column(String(100))
    color_bg: Mapped[str] = mapped_column(String(100))
    _color_text: Mapped[str] = mapped_column(String(100))
    sort_order: Mapped[str] = mapped_column(String(100))
    tools_catalogue_1_id: Mapped[int] = mapped_column(ForeignKey("tools_catalogue.id"))

class Metadata(Base):
    __tablename__ = "metadata"
    id: Mapped[int] = mapped_column(primary_key=True)
    description: Mapped[str] = mapped_column(String(100))
    provider: Mapped[str] = mapped_column(String(100))
    link: Mapped[str] = mapped_column(String(100))
    branch: Mapped[str] = mapped_column(String(100))
    scientific_reference: Mapped[str] = mapped_column(String(100))
    project_maturity: Mapped[str] = mapped_column(String(100))
    tools_catalogue_id: Mapped[int] = mapped_column(ForeignKey("tools_catalogue.id"), unique=True)

class Project(Base):
    __tablename__ = "project"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    status: Mapped[ProjectStatus] = mapped_column(Enum(ProjectStatus))

class Evaluation(Base):
    __tablename__ = "evaluation"
    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[EvaluationStatus] = mapped_column(Enum(EvaluationStatus))
    config_id: Mapped[int] = mapped_column(ForeignKey("configuration.id"))
    evaluates_id: Mapped[int] = mapped_column(ForeignKey("element.id"))
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"))

class Measure(Base):
    __tablename__ = "measure"
    id: Mapped[int] = mapped_column(primary_key=True)
    value: Mapped[str] = mapped_column(String(100))
    error: Mapped[str] = mapped_column(String(100))
    uncertainty: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(100))
    metric_id: Mapped[int] = mapped_column(ForeignKey("metric.id"))
    observation_id: Mapped[int] = mapped_column(ForeignKey("observation.id"))
    measurand_id: Mapped[int] = mapped_column(ForeignKey("element.id"))

class AssessmentElement(AbstractConcreteBase, Base):
    strict_attrs = True
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(100))

class Configuration(AssessmentElement):
    __tablename__ = "configuration"
    id: Mapped[int] = mapped_column(primary_key=True)
    __mapper_args__ = {
        "polymorphic_identity": "configuration",
        "concrete": True,
    }

class Observation(AssessmentElement):
    __tablename__ = "observation"
    id: Mapped[int] = mapped_column(primary_key=True)
    observer: Mapped[str] = mapped_column(String(100))
    whenObserved: Mapped[dt_datetime] = mapped_column(DateTime)
    tool_id: Mapped[int] = mapped_column(ForeignKey("tool.id"))
    eval_id: Mapped[int] = mapped_column(ForeignKey("evaluation.id"))
    dataset_id: Mapped[int] = mapped_column(ForeignKey("dataset.id"))
    __mapper_args__ = {
        "polymorphic_identity": "observation",
        "concrete": True,
    }

class Element(AssessmentElement):
    __tablename__ = "element"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), nullable=True)
    type_spec: Mapped[str] = mapped_column(String(50))
    __mapper_args__ = {
        "polymorphic_identity": "element",
        "polymorphic_on": "type_spec",
    }

class Feature(Element):
    __tablename__ = "feature"
    id: Mapped[int] = mapped_column(ForeignKey("element.id"), primary_key=True)
    feature_type: Mapped[str] = mapped_column(String(100))
    min_value: Mapped[float] = mapped_column(Float)
    max_value: Mapped[float] = mapped_column(Float)
    features_id: Mapped[int] = mapped_column(ForeignKey("datashape.id"))
    __mapper_args__ = {
        "polymorphic_identity": "feature",
    }

class Dataset(Element):
    __tablename__ = "dataset"
    id: Mapped[int] = mapped_column(ForeignKey("element.id"), primary_key=True)
    source: Mapped[str] = mapped_column(String(100))
    version: Mapped[str] = mapped_column(String(100))
    licensing: Mapped[LicensingType] = mapped_column(Enum(LicensingType))
    dataset_type: Mapped[DatasetType] = mapped_column(Enum(DatasetType))
    datashape_id: Mapped[int] = mapped_column(ForeignKey("datashape.id"))
    __mapper_args__ = {
        "polymorphic_identity": "dataset",
    }

class AISystem(Element):
    __tablename__ = "aisystem"
    id: Mapped[int] = mapped_column(ForeignKey("element.id"), primary_key=True)
    settings: Mapped[str] = mapped_column(String(100))
    data: Mapped[str] = mapped_column(String(100))
    source: Mapped[str] = mapped_column(String(100))
    licensing: Mapped[LicensingType] = mapped_column(Enum(LicensingType))
    version: Mapped[str] = mapped_column(String(100))
    __mapper_args__ = {
        "polymorphic_identity": "aisystem",
    }

class Tool(AssessmentElement):
    __tablename__ = "tool"
    id: Mapped[int] = mapped_column(primary_key=True)
    licensing: Mapped[LicensingType] = mapped_column(Enum(LicensingType))
    verification_type: Mapped[VerificationType] = mapped_column(Enum(VerificationType))
    provider: Mapped[str] = mapped_column(String(100))
    project: Mapped[str] = mapped_column(String(100))
    branch: Mapped[str] = mapped_column(String(100))
    version: Mapped[str] = mapped_column(String(100))
    project_maturity: Mapped[str] = mapped_column(String(100))
    scientific_reference: Mapped[str] = mapped_column(String(100))
    verification_targets: Mapped[TagsVerificationTarget] = mapped_column(Enum(TagsVerificationTarget))
    sector: Mapped[TagsSector] = mapped_column(Enum(TagsSector))
    target_system: Mapped[TagsTargetSystem] = mapped_column(Enum(TagsTargetSystem))
    target_legal_requirements: Mapped[str] = mapped_column(String(100))
    __mapper_args__ = {
        "polymorphic_identity": "tool",
        "concrete": True,
    }

class ConfParam(AssessmentElement):
    __tablename__ = "confparam"
    id: Mapped[int] = mapped_column(primary_key=True)
    param_type: Mapped[str] = mapped_column(String(100))
    value: Mapped[str] = mapped_column(String(100))
    conf_id: Mapped[int] = mapped_column(ForeignKey("configuration.id"))
    __mapper_args__ = {
        "polymorphic_identity": "confparam",
        "concrete": True,
    }

class Metric(AssessmentElement):
    __tablename__ = "metric"
    id: Mapped[int] = mapped_column(primary_key=True)
    type_spec: Mapped[str] = mapped_column(String(50))
    __mapper_args__ = {
        "polymorphic_identity": "metric",
        "polymorphic_on": "type_spec",
    }

class Direct(Metric):
    __tablename__ = "direct"
    id: Mapped[int] = mapped_column(ForeignKey("metric.id"), primary_key=True)
    __mapper_args__ = {
        "polymorphic_identity": "direct",
    }

class Derived(Metric):
    __tablename__ = "derived"
    id: Mapped[int] = mapped_column(ForeignKey("metric.id"), primary_key=True)
    expression: Mapped[str] = mapped_column(String(100))
    __mapper_args__ = {
        "polymorphic_identity": "derived",
    }

class MetricCategory(AssessmentElement):
    __tablename__ = "metriccategory"
    id: Mapped[int] = mapped_column(primary_key=True)
    __mapper_args__ = {
        "polymorphic_identity": "metriccategory",
        "concrete": True,
    }


#--- Relationships of the comments table
Comments.user: Mapped["User"] = relationship("User", back_populates="comments", foreign_keys=[Comments.user_id])

#--- Relationships of the user table
User.comments: Mapped[List["Comments"]] = relationship("Comments", back_populates="user", foreign_keys=[Comments.user_id])

#--- Relationships of the legalrequirement table
LegalRequirement.project_1: Mapped["Project"] = relationship("Project", back_populates="legal_requirements", foreign_keys=[LegalRequirement.project_1_id])

#--- Relationships of the tools_catalogue table
Tools_catalogue.tags: Mapped[List["Tags"]] = relationship("Tags", back_populates="tools_catalogue_1", foreign_keys=[Tags.tools_catalogue_1_id])
Tools_catalogue.metadata: Mapped["Metadata"] = relationship("Metadata", back_populates="tools_catalogue", foreign_keys=[Metadata.tools_catalogue_id])

#--- Relationships of the datashape table
Datashape.dataset_1: Mapped[List["Dataset"]] = relationship("Dataset", back_populates="datashape", foreign_keys=[Dataset.datashape_id])
Datashape.f_features: Mapped[List["Feature"]] = relationship("Feature", back_populates="features", foreign_keys=[Feature.features_id])
Datashape.f_date: Mapped[List["Feature"]] = relationship("Feature", secondary=datashape_feature, back_populates="date")

#--- Relationships of the tags table
Tags.tools_catalogue_1: Mapped["Tools_catalogue"] = relationship("Tools_catalogue", back_populates="tags", foreign_keys=[Tags.tools_catalogue_1_id])

#--- Relationships of the metadata table
Metadata.tools_catalogue: Mapped["Tools_catalogue"] = relationship("Tools_catalogue", back_populates="metadata", foreign_keys=[Metadata.tools_catalogue_id])

#--- Relationships of the project table
Project.legal_requirements: Mapped[List["LegalRequirement"]] = relationship("LegalRequirement", back_populates="project_1", foreign_keys=[LegalRequirement.project_1_id])
Project.eval: Mapped[List["Evaluation"]] = relationship("Evaluation", back_populates="project", foreign_keys=[Evaluation.project_id])
Project.involves: Mapped[List["Element"]] = relationship("Element", back_populates="project", foreign_keys=[Element.project_id])

#--- Relationships of the evaluation table
Evaluation.observations: Mapped[List["Observation"]] = relationship("Observation", back_populates="eval", foreign_keys=[Observation.eval_id])
Evaluation.ref: Mapped[List["Element"]] = relationship("Element", secondary=evaluation_element, back_populates="eval")
Evaluation.config: Mapped["Configuration"] = relationship("Configuration", back_populates="eval", foreign_keys=[Evaluation.config_id])
Evaluation.evaluates: Mapped["Element"] = relationship("Element", back_populates="evalu", foreign_keys=[Evaluation.evaluates_id])
Evaluation.project: Mapped["Project"] = relationship("Project", back_populates="eval", foreign_keys=[Evaluation.project_id])

#--- Relationships of the measure table
Measure.metric: Mapped["Metric"] = relationship("Metric", back_populates="measures", foreign_keys=[Measure.metric_id])
Measure.observation: Mapped["Observation"] = relationship("Observation", back_populates="measures", foreign_keys=[Measure.observation_id])
Measure.measurand: Mapped["Element"] = relationship("Element", back_populates="measure", foreign_keys=[Measure.measurand_id])

#--- Relationships of the configuration table
Configuration.eval: Mapped[List["Evaluation"]] = relationship("Evaluation", back_populates="config", foreign_keys=[Evaluation.config_id])
Configuration.params: Mapped[List["ConfParam"]] = relationship("ConfParam", back_populates="conf", foreign_keys=[ConfParam.conf_id])

#--- Relationships of the observation table
Observation.tool: Mapped["Tool"] = relationship("Tool", back_populates="observation_1", foreign_keys=[Observation.tool_id])
Observation.eval: Mapped["Evaluation"] = relationship("Evaluation", back_populates="observations", foreign_keys=[Observation.eval_id])
Observation.measures: Mapped[List["Measure"]] = relationship("Measure", back_populates="observation", foreign_keys=[Measure.observation_id])
Observation.dataset: Mapped["Dataset"] = relationship("Dataset", back_populates="observation_2", foreign_keys=[Observation.dataset_id])

#--- Relationships of the element table
Element.project: Mapped["Project"] = relationship("Project", back_populates="involves", foreign_keys=[Element.project_id])
Element.measure: Mapped[List["Measure"]] = relationship("Measure", back_populates="measurand", foreign_keys=[Measure.measurand_id])
Element.evalu: Mapped[List["Evaluation"]] = relationship("Evaluation", back_populates="evaluates", foreign_keys=[Evaluation.evaluates_id])
Element.eval: Mapped[List["Evaluation"]] = relationship("Evaluation", secondary=evaluation_element, back_populates="ref")

#--- Relationships of the feature table
Feature.date: Mapped[List["Datashape"]] = relationship("Datashape", secondary=datashape_feature, back_populates="f_date")
Feature.features: Mapped["Datashape"] = relationship("Datashape", back_populates="f_features", foreign_keys=[Feature.features_id])

#--- Relationships of the dataset table
Dataset.models: Mapped[List["AISystem"]] = relationship("AISystem", secondary=aisystem_dataset, back_populates="dataset")
Dataset.observation_2: Mapped[List["Observation"]] = relationship("Observation", back_populates="dataset", foreign_keys=[Observation.dataset_id])
Dataset.datashape: Mapped["Datashape"] = relationship("Datashape", back_populates="dataset_1", foreign_keys=[Dataset.datashape_id])

#--- Relationships of the aisystem table
AISystem.dataset: Mapped[List["Dataset"]] = relationship("Dataset", secondary=aisystem_dataset, back_populates="models")

#--- Relationships of the tool table
Tool.observation_1: Mapped[List["Observation"]] = relationship("Observation", back_populates="tool", foreign_keys=[Observation.tool_id])

#--- Relationships of the confparam table
ConfParam.conf: Mapped["Configuration"] = relationship("Configuration", back_populates="params", foreign_keys=[ConfParam.conf_id])

#--- Relationships of the metric table
Metric.measures: Mapped[List["Measure"]] = relationship("Measure", back_populates="metric", foreign_keys=[Measure.metric_id])
Metric.category: Mapped[List["MetricCategory"]] = relationship("MetricCategory", secondary=metriccategory_metric, back_populates="metrics")
Metric.derivedBy: Mapped[List["Derived"]] = relationship("Derived", secondary=derived_metric, back_populates="baseMetric")

#--- Relationships of the derived table
Derived.baseMetric: Mapped[List["Metric"]] = relationship("Metric", secondary=derived_metric, back_populates="derivedBy")

#--- Relationships of the metriccategory table
MetricCategory.metrics: Mapped[List["Metric"]] = relationship("Metric", secondary=metriccategory_metric, back_populates="category")

# Database connection
DATABASE_URL = "sqlite:///DPIA.db"  # SQLite connection
# engine = create_engine(DATABASE_URL, echo=True)

# Create tables in the database
# Base.metadata.create_all(engine, checkfirst=True)