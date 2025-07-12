from openai import AsyncOpenAI
import tiktoken
from typing import Dict, Any
import time
from decimal import Decimal
import logging
import json

from api.config import settings

logger = logging.getLogger(__name__)


class OpenAIClient:
    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model_pricing = {
            "gpt-4o": {"input": 0.005, "output": 0.015},  # per 1K tokens
            "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
            "gpt-4-turbo": {"input": 0.01, "output": 0.03},
            "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},
        }
    
    async def test_prompt(self, prompt: str, model: str = "gpt-4o") -> Dict[str, Any]:
        """Test a prompt and return response with metrics"""
        try:
            start_time = time.time()
            
            # Create completion
            response = await self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=1000
            )
            
            end_time = time.time()
            response_time_ms = int((end_time - start_time) * 1000)
            
            # Extract metrics
            usage = response.usage
            tokens_used = usage.total_tokens
            
            # Calculate cost
            pricing = self.model_pricing.get(model, self.model_pricing["gpt-4o"])
            input_cost = (usage.prompt_tokens / 1000) * pricing["input"]
            output_cost = (usage.completion_tokens / 1000) * pricing["output"]
            total_cost = Decimal(str(input_cost + output_cost))
            
            return {
                "response": response.choices[0].message.content,
                "tokens_used": tokens_used,
                "response_time_ms": response_time_ms,
                "estimated_cost": total_cost,
                "model": model,
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens
            }
            
        except Exception as e:
            logger.error(f"Error testing prompt with OpenAI: {e}")
            raise
    
    async def validate_prompt(self, template: str, variables: list) -> Dict[str, Any]:
        """Validate a prompt template and estimate costs"""
        try:
            # Create a sample filled prompt
            sample_prompt = template
            for var in variables:
                sample_prompt = sample_prompt.replace(
                    f"{{{var['name']}}}", 
                    var.get('example', f"[{var['name']}]")
                )
            
            # Count tokens
            encoding = tiktoken.encoding_for_model("gpt-4o")
            token_count = len(encoding.encode(sample_prompt))
            
            # Estimate costs for different models
            cost_estimates = {}
            for model, pricing in self.model_pricing.items():
                # Assume average response is 2x input tokens
                input_cost = (token_count / 1000) * pricing["input"]
                output_cost = (token_count * 2 / 1000) * pricing["output"]
                cost_estimates[model] = {
                    "min": float(input_cost),
                    "max": float(input_cost + output_cost),
                    "average": float(input_cost + output_cost / 2)
                }
            
            return {
                "is_valid": True,
                "estimated_tokens": token_count,
                "cost_estimates": cost_estimates,
                "sample_prompt": sample_prompt[:500] + "..." if len(sample_prompt) > 500 else sample_prompt
            }
            
        except Exception as e:
            logger.error(f"Error validating prompt: {e}")
            return {
                "is_valid": False,
                "error": str(e)
            }
    
    async def generate_prompt_suggestions(self, category: str, use_case: str) -> list:
        """Generate prompt suggestions based on category and use case"""
        try:
            system_prompt = f"""You are an expert prompt engineer. Generate 3 high-quality prompt templates 
            for the category '{category}' and use case '{use_case}'. 
            
            Each prompt should:
            1. Be specific and actionable
            2. Include variables in {{variable_name}} format
            3. Be optimized for business use cases
            4. Include clear instructions
            
            Return as JSON array with title, template, and variables fields."""
            
            response = await self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Generate prompts for {category} - {use_case}"}
                ],
                temperature=0.8,
                response_format={"type": "json_object"}
            )
            
            suggestions = response.choices[0].message.content
            return suggestions
            
        except Exception as e:
            logger.error(f"Error generating prompt suggestions: {e}")
            return []
    
    async def analyze_prompt_performance(self, prompt: str, test_cases: list) -> Dict[str, Any]:
        """Analyze prompt performance across multiple test cases"""
        try:
            results = []
            total_tokens = 0
            total_time = 0
            
            for test_case in test_cases[:5]:  # Limit to 5 test cases
                result = await self.test_prompt(
                    prompt.format(**test_case),
                    model="gpt-4o-mini"  # Use cheaper model for analysis
                )
                results.append({
                    "input": test_case,
                    "output": result["response"][:200] + "...",
                    "tokens": result["tokens_used"],
                    "time_ms": result["response_time_ms"]
                })
                total_tokens += result["tokens_used"]
                total_time += result["response_time_ms"]
            
            # Analyze consistency and quality
            consistency_score = self._calculate_consistency(results)
            
            return {
                "test_results": results,
                "average_tokens": total_tokens / len(results),
                "average_time_ms": total_time / len(results),
                "consistency_score": consistency_score,
                "recommendations": self._generate_recommendations(results, consistency_score)
            }
            
        except Exception as e:
            logger.error(f"Error analyzing prompt performance: {e}")
            raise
    
    def _calculate_consistency(self, results: list) -> float:
        """Calculate consistency score based on response similarity"""
        # Simple implementation - could be enhanced with embeddings
        if len(results) < 2:
            return 1.0
        
        # Check response length variance
        lengths = [len(r["output"]) for r in results]
        avg_length = sum(lengths) / len(lengths)
        variance = sum((l - avg_length) ** 2 for l in lengths) / len(lengths)
        
        # Lower variance = higher consistency
        consistency = max(0, 1 - (variance / (avg_length ** 2)))
        return round(consistency, 2)
    
    def _generate_recommendations(self, results: list, consistency_score: float) -> list:
        """Generate recommendations based on analysis"""
        recommendations = []
        
        if consistency_score < 0.7:
            recommendations.append("Consider adding more specific instructions to improve consistency")
        
        avg_tokens = sum(r["tokens"] for r in results) / len(results)
        if avg_tokens > 1000:
            recommendations.append("Prompt generates lengthy responses - consider adding length constraints")
        
        avg_time = sum(r["time_ms"] for r in results) / len(results)
        if avg_time > 3000:
            recommendations.append("Response time is high - consider simplifying the prompt")
        
        return recommendations