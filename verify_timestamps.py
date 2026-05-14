#!/usr/bin/env python
"""Verify exit order timestamps in backtest journal"""
import json
from datetime import datetime

with open('logs/strategy_runtime/intrabar_exit_1m_verify_journal.jsonl', 'r') as f:
    exit_debug_events = []
    sell_order_events = []
    
    for line in f:
        data = json.loads(line)
        event = data.get('event', '')
        ts = data.get('ts', '')
        event_ts = data.get('event_ts', '')
        
        if event == 'FORCE_EXIT_DEBUG':
            should_exit = data.get('data', {}).get('should_exit', False)
            as_of_time = data.get('data', {}).get('as_of_time', '')
            if should_exit:
                exit_debug_events.append({
                    'ts': ts,
                    'event_ts': event_ts,
                    'as_of_time': as_of_time
                })
                print(f'FORCE_EXIT_DEBUG (should_exit=True):')
                print(f'  ts={ts}')
                print(f'  event_ts={event_ts}')
                print(f'  as_of_time={as_of_time}')
                print()
        
        elif event == 'ORDER' and '"side": "SELL"' in line:
            order_data = data.get('data', {})
            print(f'SELL ORDER:')
            print(f'  ts={ts}')
            print(f'  order_id={order_data.get("order_id")}')
            print()
            sell_order_events.append({
                'ts': ts,
                'order_id': order_data.get('order_id')
            })

print(f"\nTotal FORCE_EXIT_DEBUG events: {len(exit_debug_events)}")
print(f"Total SELL ORDER events: {len(sell_order_events)}")
