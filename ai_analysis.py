"""
AI Trading Analysis Module

This module provides AI-powered analysis of trading performance using OpenAI's GPT models.
It analyzes individual trades, daily performance, and provides actionable feedback.
"""

import openai
import os
from datetime import datetime, timedelta
import json
import re
from models import TradeAnalysis, db

class TradingAIAnalyzer:
    """AI-powered trading analysis using OpenAI GPT models"""
    
    def __init__(self):
        """Initialize the AI analyzer with OpenAI API key"""
        self.api_key = os.getenv('OPENAI_API_KEY')
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set")
        
        openai.api_key = self.api_key
        self.model = "gpt-4"  # Use GPT-4 for better analysis
        
    def analyze_trade(self, trade):
        """
        Analyze a single trade and provide detailed feedback
        
        Args:
            trade: Trade object from the database
            
        Returns:
            TradeAnalysis object or None if analysis fails
        """
        try:
            # Prepare trade data for analysis
            trade_data = self._prepare_trade_data(trade)
            
            # Generate analysis prompt
            prompt = self._create_trade_analysis_prompt(trade_data)
            
            # Get AI analysis
            response = openai.ChatCompletion.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._get_system_prompt()},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=2000,
                temperature=0.7
            )
            
            analysis_text = response.choices[0].message.content
            
            # Parse the analysis
            parsed_analysis = self._parse_analysis(analysis_text)
            
            # Create or update TradeAnalysis record
            analysis = TradeAnalysis.query.filter_by(trade_id=trade.id).first()
            if not analysis:
                analysis = TradeAnalysis(
                    trade_id=trade.id,
                    user_id=trade.user_id,
                    ai_model_used=self.model
                )
            
            # Update analysis fields
            analysis.overall_score = parsed_analysis.get('overall_score', 5)
            analysis.entry_analysis = parsed_analysis.get('entry_analysis', '')
            analysis.exit_analysis = parsed_analysis.get('exit_analysis', '')
            analysis.risk_analysis = parsed_analysis.get('risk_analysis', '')
            analysis.market_context = parsed_analysis.get('market_context', '')
            analysis.options_analysis = parsed_analysis.get('options_analysis', '')
            
            # Set JSON fields
            analysis.set_strengths(parsed_analysis.get('strengths', []))
            analysis.set_weaknesses(parsed_analysis.get('weaknesses', []))
            analysis.set_improvement_areas(parsed_analysis.get('improvement_areas', []))
            analysis.set_actionable_drills(parsed_analysis.get('actionable_drills', []))
            analysis.set_recommendations(parsed_analysis.get('recommendations', []))
            analysis.set_key_lessons(parsed_analysis.get('key_lessons', []))
            
            # Save to database
            db.session.add(analysis)
            trade.is_analyzed = True
            db.session.commit()
            
            return analysis
            
        except Exception as e:
            print(f"Error analyzing trade {trade.id}: {str(e)}")
            return None
    
    def analyze_daily_performance(self, journal_entry, trades):
        """
        Analyze daily trading performance
        
        Args:
            journal_entry: TradingJournal object
            trades: List of Trade objects for the day
            
        Returns:
            Dict with analysis results
        """
        try:
            # Prepare daily data
            daily_data = self._prepare_daily_data(journal_entry, trades)
            
            # Generate daily analysis prompt
            prompt = self._create_daily_analysis_prompt(daily_data)
            
            # Get AI analysis
            response = openai.ChatCompletion.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._get_daily_system_prompt()},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=1500,
                temperature=0.7
            )
            
            analysis_text = response.choices[0].message.content
            
            # Parse daily analysis
            parsed_analysis = self._parse_daily_analysis(analysis_text)
            
            return {
                'feedback': analysis_text,
                'daily_score': parsed_analysis.get('daily_score', 5),
                'key_insights': parsed_analysis.get('key_insights', []),
                'tomorrow_focus': parsed_analysis.get('tomorrow_focus', [])
            }
            
        except Exception as e:
            print(f"Error analyzing daily performance: {str(e)}")
            return None
    
    def _prepare_trade_data(self, trade):
        """Prepare trade data for AI analysis"""
        data = {
            'symbol': trade.symbol,
            'trade_type': trade.trade_type,
            'entry_date': trade.entry_date.strftime('%Y-%m-%d %H:%M') if trade.entry_date else None,
            'exit_date': trade.exit_date.strftime('%Y-%m-%d %H:%M') if trade.exit_date else None,
            'entry_price': trade.entry_price,
            'exit_price': trade.exit_price,
            'quantity': trade.quantity,
            'profit_loss': trade.profit_loss,
            'profit_loss_percent': trade.profit_loss_percent,
            'setup_type': trade.setup_type,
            'market_condition': trade.market_condition,
            'timeframe': trade.timeframe,
            'entry_reason': trade.entry_reason,
            'exit_reason': trade.exit_reason,
            'notes': trade.notes,
            'tags': trade.tags,
            'stop_loss': trade.stop_loss,
            'take_profit': trade.take_profit,
            'risk_amount': trade.risk_amount,
            'hold_time': str(trade.get_hold_time()) if trade.exit_date else None,
            'risk_reward_ratio': trade.get_risk_reward_ratio(),
            'is_winner': trade.is_winner() if trade.exit_price else None
        }
        
        # Add options-specific data
        if trade.is_option_trade():
            data.update({
                'is_option_trade': True,
                'is_spread_trade': trade.is_spread_trade(),
                'strike_price': trade.strike_price,
                'expiration_date': trade.expiration_date.strftime('%Y-%m-%d') if trade.expiration_date else None,
                'option_type': trade.option_type,
                'premium_paid': trade.premium_paid,
                'implied_volatility': trade.implied_volatility,
                'underlying_price_at_entry': trade.underlying_price_at_entry,
                'underlying_price_at_exit': trade.underlying_price_at_exit,
                'days_to_expiration': trade.get_days_to_expiration(),
                'moneyness': trade.get_moneyness(),
                'intrinsic_value': trade.get_intrinsic_value(),
                'time_value': trade.get_time_value(),
                'delta': trade.delta,
                'gamma': trade.gamma,
                'theta': trade.theta,
                'vega': trade.vega
            })
            
            # Add spread-specific data
            if trade.is_spread_trade():
                data.update({
                    'spread_type': trade.spread_type,
                    'long_strike': trade.long_strike,
                    'short_strike': trade.short_strike,
                    'long_premium': trade.long_premium,
                    'short_premium': trade.short_premium,
                    'net_credit': trade.net_credit,
                    'max_profit': trade.max_profit,
                    'max_loss': trade.max_loss,
                    'breakeven_price': trade.breakeven_price
                })
        
        return data
    
    def _prepare_daily_data(self, journal_entry, trades):
        """Prepare daily data for AI analysis"""
        return {
            'date': journal_entry.journal_date.strftime('%Y-%m-%d'),
            'daily_pnl': journal_entry.daily_pnl,
            'market_outlook': journal_entry.market_outlook,
            'daily_goals': journal_entry.daily_goals,
            'what_went_well': journal_entry.what_went_well,
            'what_went_wrong': journal_entry.what_went_wrong,
            'emotional_state': journal_entry.emotional_state,
            'stress_level': journal_entry.stress_level,
            'discipline_score': journal_entry.discipline_score,
            'market_trend': journal_entry.market_trend,
            'volatility': journal_entry.volatility,
            'trades_count': len(trades),
            'winning_trades': len([t for t in trades if t.is_winner()]),
            'losing_trades': len([t for t in trades if t.profit_loss and t.profit_loss < 0]),
            'total_pnl': sum(t.profit_loss for t in trades if t.profit_loss),
            'trade_types': [t.trade_type for t in trades],
            'setups': [t.setup_type for t in trades if t.setup_type]
        }
    
    def _get_system_prompt(self):
        """Get the system prompt for trade analysis"""
        return """You are an expert trading coach and analyst with 20+ years of experience in stocks, options, and derivatives trading. Your role is to provide detailed, actionable analysis of individual trades to help traders improve their performance.

Key areas to analyze:
1. ENTRY ANALYSIS: Timing, setup quality, market context, risk/reward assessment
2. EXIT ANALYSIS: Exit timing, profit-taking vs stop-loss execution, missed opportunities
3. RISK MANAGEMENT: Position sizing, stop-loss placement, risk/reward ratios
4. OPTIONS ANALYSIS: For options trades, analyze Greeks, time decay, volatility, moneyness
5. SPREAD ANALYSIS: For credit spreads, analyze strike selection, credit received, risk management
6. MARKET CONTEXT: How well the trade aligned with market conditions
7. PSYCHOLOGY: Emotional factors, discipline, plan adherence

Provide specific, actionable feedback that helps the trader improve. Be constructive but honest about mistakes. Focus on education and skill development."""

    def _get_daily_system_prompt(self):
        """Get the system prompt for daily analysis"""
        return """You are an expert trading coach analyzing daily trading performance. Focus on overall execution, emotional state, market adaptation, and areas for improvement. Provide actionable feedback for tomorrow's trading session."""

    def _create_trade_analysis_prompt(self, trade_data):
        """Create the analysis prompt for a single trade"""
        prompt = f"""Analyze this trade in detail:

TRADE SUMMARY:
- Symbol: {trade_data['symbol']}
- Type: {trade_data['trade_type']}
- Entry: ${trade_data['entry_price']} on {trade_data['entry_date']}
- Exit: ${trade_data['exit_price']} on {trade_data['exit_date']} (if closed)
- Quantity: {trade_data['quantity']}
- P&L: ${trade_data['profit_loss']} ({trade_data['profit_loss_percent']}%)
- Setup: {trade_data['setup_type']}
- Market Condition: {trade_data['market_condition']}
- Timeframe: {trade_data['timeframe']}
- Hold Time: {trade_data['hold_time']}

TRADE REASONING:
Entry Reason: {trade_data['entry_reason']}
Exit Reason: {trade_data['exit_reason']}
Notes: {trade_data['notes']}
Tags: {trade_data['tags']}

RISK MANAGEMENT:
- Stop Loss: ${trade_data['stop_loss']}
- Take Profit: ${trade_data['take_profit']}
- Risk Amount: ${trade_data['risk_amount']}
- Risk/Reward Ratio: {trade_data['risk_reward_ratio']}
"""

        # Add options-specific analysis
        if trade_data.get('is_option_trade'):
            prompt += f"""
OPTIONS DETAILS:
- Strike Price: ${trade_data['strike_price']}
- Expiration: {trade_data['expiration_date']}
- Option Type: {trade_data['option_type']}
- Premium Paid: ${trade_data['premium_paid']}
- Implied Volatility: {trade_data['implied_volatility']}%
- Underlying at Entry: ${trade_data['underlying_price_at_entry']}
- Underlying at Exit: ${trade_data['underlying_price_at_exit']}
- Days to Expiration: {trade_data['days_to_expiration']}
- Moneyness: {trade_data['moneyness']}
- Intrinsic Value: ${trade_data['intrinsic_value']}
- Time Value: ${trade_data['time_value']}
- Delta: {trade_data['delta']}
- Gamma: {trade_data['gamma']}
- Theta: {trade_data['theta']}
- Vega: {trade_data['vega']}
"""

        # Add spread-specific analysis
        if trade_data.get('is_spread_trade'):
            prompt += f"""
SPREAD DETAILS:
- Spread Type: {trade_data['spread_type']}
- Short Strike: ${trade_data['short_strike']} (Premium: ${trade_data['short_premium']})
- Long Strike: ${trade_data['long_strike']} (Premium: ${trade_data['long_premium']})
- Net Credit: ${trade_data['net_credit']}
- Max Profit: ${trade_data['max_profit']}
- Max Loss: ${trade_data['max_loss']}
- Breakeven: ${trade_data['breakeven_price']}
"""

        prompt += """
Please provide a comprehensive analysis with:

1. OVERALL SCORE (1-10): Rate the trade execution quality
2. STRENGTHS: What was done well (list 2-4 points)
3. WEAKNESSES: What could be improved (list 2-4 points)
4. ENTRY ANALYSIS: Detailed analysis of entry timing and setup
5. EXIT ANALYSIS: Analysis of exit execution (if applicable)
6. RISK ANALYSIS: Assessment of risk management
7. MARKET CONTEXT: How well the trade fit market conditions
8. OPTIONS ANALYSIS: Options-specific feedback (if applicable)
9. IMPROVEMENT AREAS: Specific areas to focus on (list 2-3 points)
10. ACTIONABLE DRILLS: Specific exercises to improve (list 2-3 points)
11. RECOMMENDATIONS: Specific advice for similar future trades
12. KEY LESSONS: Main takeaways from this trade

Format your response clearly with section headers."""

        return prompt

    def _create_daily_analysis_prompt(self, daily_data):
        """Create the analysis prompt for daily performance"""
        return f"""Analyze this trading day:

DATE: {daily_data['date']}
DAILY P&L: ${daily_data['daily_pnl']}
TRADES: {daily_data['trades_count']} total ({daily_data['winning_trades']} wins, {daily_data['losing_trades']} losses)

MORNING PLAN:
Market Outlook: {daily_data['market_outlook']}
Daily Goals: {daily_data['daily_goals']}

END OF DAY REFLECTION:
What Went Well: {daily_data['what_went_well']}
What Went Wrong: {daily_data['what_went_wrong']}

PSYCHOLOGY:
Emotional State: {daily_data['emotional_state']}
Stress Level: {daily_data['stress_level']}/10
Discipline Score: {daily_data['discipline_score']}/10

MARKET CONDITIONS:
Trend: {daily_data['market_trend']}
Volatility: {daily_data['volatility']}

TRADE TYPES: {', '.join(daily_data['trade_types'])}
SETUPS: {', '.join(daily_data['setups'])}

Provide feedback on:
1. Overall execution quality
2. Emotional management
3. Plan adherence
4. Market adaptation
5. Areas for tomorrow's improvement
6. Daily score (1-10)

Be specific and actionable."""

    def _parse_analysis(self, analysis_text):
        """Parse the AI analysis response into structured data"""
        parsed = {}
        
        # Extract overall score
        score_match = re.search(r'(?:OVERALL SCORE|SCORE).*?(\d+)', analysis_text, re.IGNORECASE)
        if score_match:
            parsed['overall_score'] = int(score_match.group(1))
        
        # Extract sections using regex
        sections = {
            'strengths': r'STRENGTHS?:?\s*(.*?)(?=\n\d+\.|WEAKNESSES?|$)',
            'weaknesses': r'WEAKNESSES?:?\s*(.*?)(?=\n\d+\.|ENTRY ANALYSIS|$)',
            'entry_analysis': r'ENTRY ANALYSIS:?\s*(.*?)(?=\n\d+\.|EXIT ANALYSIS|$)',
            'exit_analysis': r'EXIT ANALYSIS:?\s*(.*?)(?=\n\d+\.|RISK ANALYSIS|$)',
            'risk_analysis': r'RISK ANALYSIS:?\s*(.*?)(?=\n\d+\.|MARKET CONTEXT|$)',
            'market_context': r'MARKET CONTEXT:?\s*(.*?)(?=\n\d+\.|OPTIONS ANALYSIS|$)',
            'options_analysis': r'OPTIONS ANALYSIS:?\s*(.*?)(?=\n\d+\.|IMPROVEMENT|$)',
            'improvement_areas': r'IMPROVEMENT AREAS?:?\s*(.*?)(?=\n\d+\.|ACTIONABLE|$)',
            'actionable_drills': r'ACTIONABLE DRILLS?:?\s*(.*?)(?=\n\d+\.|RECOMMENDATIONS|$)',
            'recommendations': r'RECOMMENDATIONS?:?\s*(.*?)(?=\n\d+\.|KEY LESSONS|$)',
            'key_lessons': r'KEY LESSONS?:?\s*(.*?)(?=\n\d+\.|$)'
        }
        
        for key, pattern in sections.items():
            match = re.search(pattern, analysis_text, re.IGNORECASE | re.DOTALL)
            if match:
                content = match.group(1).strip()
                if key in ['strengths', 'weaknesses', 'improvement_areas', 'actionable_drills', 'recommendations', 'key_lessons']:
                    # Parse as list
                    items = [item.strip('- ').strip() for item in content.split('\n') if item.strip() and not item.strip().startswith('OVERALL')]
                    parsed[key] = [item for item in items if len(item) > 10]  # Filter out short/empty items
                else:
                    # Parse as text
                    parsed[key] = content
        
        return parsed
    
    def _parse_daily_analysis(self, analysis_text):
        """Parse daily analysis response"""
        parsed = {}
        
        # Extract daily score
        score_match = re.search(r'(?:DAILY SCORE|SCORE).*?(\d+)', analysis_text, re.IGNORECASE)
        if score_match:
            parsed['daily_score'] = int(score_match.group(1))
        
        return parsed 