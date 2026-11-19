from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class AgentConfiguration:
    agent_id: int
    name: str
    api_key: str
    api_secret: str
    flow_id: str

    @property
    def masked_api_key(self) -> str:
        if len(self.api_key) <= 4:
            return "****"
        return f"{self.api_key[:4]}****{self.api_key[-3:]}"

    def to_public_dict(self) -> dict[str, object]:
        return {
            "id": self.agent_id,
            "agentName": self.name,
            "apiKey": self.masked_api_key,
            "apiSecret": None,
            "apiFlowId": self.flow_id,
        }


@dataclass(frozen=True)
class BusinessAgentScene:
    name: str
    aliases: tuple[str, ...] = ()

    def resolve(
        self, configurations: Mapping[str, AgentConfiguration]
    ) -> AgentConfiguration:
        for key in (self.name, *self.aliases):
            configuration = configurations.get(key)
            if configuration is not None:
                return configuration
        raise LookupError(f"agent configuration not found for scene: {self.name}")
