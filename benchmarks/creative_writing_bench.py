import json
import datetime
import tqdm
from benchmarks.base_benchmark import BaseBenchmark
from lib.run_query import run_query
from lib.util import safe_dump
from lib.creative_writing_utils_v2 import process_writing_prompt
from lib.scoring import calculate_creative_writing_score

class CreativeWritingBench(BaseBenchmark):
	def __init__(self, config, args, benchmark_config, runner):
		super().__init__(config, args, benchmark_config, runner)
		self.prompts = self.load_prompts()
		self.total_prompts = len(self.prompts) * self.benchmark_config['n_iterations']
		self.progress_bar = None

	def get_benchmark_type(self):
		return 'creative-writing'

	def update_benchmark_specific_metadata(self, metadata):
		metadata.update({
			"model_path": self.benchmark_config['model_path'],
			"lora_path": self.benchmark_config['lora_path'],
			'judge_model': self.config.get('Creative Writing Benchmark', 'judge_model'),
			"bitsandbytes_quant": self.benchmark_config['quantization']
		})

	def get_iteration_template(self):
		return {
			'individual_scores': {},
			'test_model_response': {},
			'judge_model_response': {}
		}
		
	def load_prompts(self):
		with open('data/creative_writing_prompts_v2.2.json', 'r', encoding='utf-8') as f:
			return json.load(f)

	def generate_run_index(self):
		components = [
			self.benchmark_config['run_id'],
			"creative-writing",
			self.benchmark_config['model_path'],
			self.benchmark_config['lora_path'],
			self.benchmark_config['prompt_type'],
			self.benchmark_config['quantization'],
			self.benchmark_config['inference_engine'],
			self.benchmark_config['ooba_params'],
			self.format_include_exclude_string()
		]
		components = [component if component is not None else '' for component in components]
		return "--".join(components)

	def format_include_exclude_string(self):
		include = ','.join(self.benchmark_config['include_patterns'])
		exclude = ','.join(self.benchmark_config['exclude_patterns'])
		return f"include({include})_exclude({exclude})" if include or exclude else ""

	def run(self):
		self.progress_bar = tqdm(total=self.total_prompts, desc="Creative Writing Progress", unit="prompt")
		
		for run_iter in range(1, self.benchmark_config['n_iterations'] + 1):
			print(f"Iteration {run_iter} of {self.benchmark_config['n_iterations']}")
			self.initialize_results()
			
			for prompt_id, prompt_data in self.prompts.items():
					if self.is_prompt_completed(prompt_id, run_iter):
						if self.args.v:
							print(f"Prompt {prompt_id} already complete")
						self.progress_bar.update(1)
						continue
					
					if not self.runner.model and not self.runner.ooba_instance:
						self.runner.initialize_model_or_ooba(self.benchmark_config)
					
					self.process_prompt(prompt_id, prompt_data, run_iter)
					self.progress_bar.update(1)

		self.progress_bar.close()
		self.save_results()
		self.print_results()

	def create_run_metadata(self):
		return {
			"run_id": self.benchmark_config['run_id'],
			"benchmark_type": "creative-writing",
			"total_iterations": self.benchmark_config['n_iterations'],
			"inference_engine": self.benchmark_config['inference_engine'],
			"ooba_params": self.benchmark_config['ooba_params'],
			"include_patterns": self.benchmark_config['include_patterns'],
			"exclude_patterns": self.benchmark_config['exclude_patterns'],
			"model_path": self.benchmark_config['model_path'],
			"lora_path": self.benchmark_config['lora_path'],
			"judge_model": self.config.get('Creative Writing Benchmark', 'judge_model'),
			"bitsandbytes_quant": self.benchmark_config['quantization']
		}

	def process_prompt(self, prompt_id, prompt_data, run_iter):
		scores = process_writing_prompt(
			prompt_id, prompt_data, self.benchmark_config['model_path'],
			self.benchmark_config['prompt_type'], self.runner.model, self.runner.tokenizer,
			self.results, self.run_index, str(run_iter), self.args.v, self.args.r,
			self.benchmark_config['inference_engine'], self.runner.ooba_instance,
			self.config.get_bool('Oobabooga config', 'automatically_launch_ooba'),
			self.config.get_int('Oobabooga config', 'ooba_request_timeout', 300),
			self.runner.openai_client, self.get_judge_params()
		)
		
		if scores:
			self.store_results(prompt_id, scores, run_iter)
			safe_dump(self.results, './raw_results.json')
   
	def is_prompt_completed(self, prompt_id, run_iter):
		return (self.run_index in self.results and
					str(run_iter) in self.results[self.run_index]['iterations'] and
					prompt_id in self.results[self.run_index]['iterations'][str(run_iter)]['individual_scores'])


	def get_judge_params(self):
		return {
			'judge_model_api': self.config.get('Creative Writing Benchmark', 'judge_model_api'),
			'judge_model': self.config.get('Creative Writing Benchmark', 'judge_model'),
			'judge_model_api_key': self.config.get('Creative Writing Benchmark', 'judge_model_api_key')
		}

	def store_results(self, prompt_id, scores, run_iter):
		iter_results = self.results[self.run_index]['iterations'][str(run_iter)]
		iter_results['individual_scores'][prompt_id] = scores

	def calculate_score(self):
		self.results[self.run_index]['creative_writing_score'] = calculate_creative_writing_score(
			self.run_index, self.results
		)
  
	def print_results(self):
		formatted_datetime = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
		print(f"\n----Creative Writing Benchmark Complete----")
		print(formatted_datetime)
		print('Time taken:', round((datetime.datetime.now() - self.start_time).total_seconds() / 60, 1), 'mins')
		print('Prompt Format:', self.benchmark_config['prompt_type'])
		print('Model:', self.benchmark_config['model_path'])
		if self.benchmark_config['lora_path']:
			print('Lora:', self.benchmark_config['lora_path'])

		score = calculate_creative_writing_score(self.run_index, self.results, self.runner.RAW_RESULTS_PATH)
		print('Creative Writing Score:', score)
		print('Judge:', self.config.get('Creative Writing Benchmark', 'judge_model'))

	def save_results(self):
		safe_dump(self.results, './raw_results.json')