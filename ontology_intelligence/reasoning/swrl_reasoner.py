import logging
from owlready2 import Imp, sync_reasoner_pellet, sync_reasoner_hermit

logger = logging.getLogger(__name__)

class SWRLReasoner:
    def __init__(self, onto):
        self.onto = onto
        self.rules = []
        self._owlready_rules = []
    
    def load_rules(self, swrl_rules_data):
        """加载从模型配置中获取的 SWRL 规则列表"""
        for rule_data in swrl_rules_data:
            if rule_data.get("enabled", True):
                self.rules.append(rule_data)
                
    def apply_rules(self):
        """将规则转换为 owlready2 的 Imp 对象并应用到本体中"""
        with self.onto:
            for i, rule in enumerate(self.rules):
                try:
                    # 将前后件组合成标准 SWRL 字符串：body -> head
                    # 例：Person(?p) ^ hasAge(?p, ?age) -> Adult(?p)
                    # body: "Person(?p), hasAge(?p, ?age)" -> head: "Adult(?p)"
                    # Owlready2 中使用逗号分隔，并使用 `->` 连接
                    body_str = rule.get("body", "").strip()
                    head_str = rule.get("head", "").strip()
                    
                    if not body_str or not head_str:
                        continue
                        
                    # Owlready2 创建规则
                    # 注意：在 Owlready2 中，创建规则字符串可能受限于已加载的词汇。
                    rule_str = f"{body_str} -> {head_str}"
                    owl_rule = Imp()
                    owl_rule.set_as_rule(rule_str)
                    self._owlready_rules.append(owl_rule)
                    logger.info(f"成功加载 SWRL 规则: {rule.get('name')}")
                    
                except Exception as e:
                    logger.error(f"解析/应用 SWRL 规则 '{rule.get('name')}' 失败: {e}")

    def reason(self, reasoner_type="hermit"):
        """执行推理
        推荐使用 pellet 来更好地支持 SWRL，但 hermit 也能支持部分
        """
        self.apply_rules()
        
        try:
            with self.onto:
                if reasoner_type.lower() == "pellet":
                    sync_reasoner_pellet(infer_property_values=True, infer_data_property_values=True)
                else:
                    sync_reasoner_hermit(infer_property_values=True)
            logger.info("SWRL 规则推理完成")
            return True, "推理成功"
        except Exception as e:
            logger.error(f"SWRL 规则推理失败: {e}")
            return False, str(e)
